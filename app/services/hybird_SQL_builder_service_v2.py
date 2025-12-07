import json

class HybridSQLBuilder:
    def __init__(self):
        # 1. 定義靜態的映射表 (Mappings)
        self.field_mapping = {
            "id": "p.id", "name": "p.name", "address": "p.address", "rating": "p.rating",
            "service_tags": "GROUP_CONCAT(tow.tag_content)",
            "merchant_category": "GROUP_CONCAT(mc.name)"
        }
        self.sql_where_mapping = {
            "address": "p.address", "merchant_category": "mc.name", 
            "service_tags": "tow.tag_content", "rating": "p.rating"
        }
        self.vector_fields = {"cuisine_type", "flavor","food_type"}
    # 只負責看懂 JSON，告訴你需不需要跑向量搜尋
    def analyze_intent(self, json_input):
        """
        第一階段：解析意圖
        回傳：一個字典，包含 SQL 所需的結構 (Plan) 以及 向量搜尋的需求 (Vector Intent)
        """
        plan = {
            "select_fields": ["p.id", "p.name", "p.address", "p.rating"],
            "sort_clauses": [],
            "sql_where_logic": None, # 這裡只存邏輯樹，不存 SQL 字串
            "query_params": {},
            "vector_needed": False,
            "vector_keywords": [] # 紀錄需要向量搜尋的關鍵字
        }

        # A. 處理 Select 欄位
        for info in json_input.get("info_needed", []):
            if info in self.field_mapping and self.field_mapping[info] not in plan["select_fields"]:
                plan["select_fields"].append(f"{self.field_mapping[info]} AS {info}")

        # B. 處理 Sort
        for s in json_input.get("sort_conditions", []):
            plan["sort_clauses"].append(f"p.{s['field']} {s['method']}")

        # C. 預先掃描邏輯樹，分離 SQL 條件與向量條件
        # 我們把原始 logic_tree 存下來，但在 build_sql 時才遞迴生成
        # 這裡先掃描是否有向量需求
        self._scan_for_vector_intent(json_input.get("logic_tree", {}), plan)

        # 把原始邏輯樹存入 plan，留給第二階段用
        plan["raw_logic_tree"] = json_input.get("logic_tree", {})
        
        return plan
    
    def _scan_for_vector_intent(self, node, plan):
        """輔助函式：遞迴掃描邏輯樹，看看有沒有向量欄位"""
        if not node: return

        if "conditions" in node:
            for child in node["conditions"]:
                self._scan_for_vector_intent(child, plan)
        else:
            # 這是葉節點
            key = list(node.keys())[0]
            if key in self.vector_fields:
                plan["vector_needed"] = True
                plan["vector_keywords"].append(node[key]["value"])

    def build_sql(self, plan, vector_result_ids=None):
        """
        第二階段：生成 SQL
        參數：
          plan: 第一階段產出的計畫
          vector_result_ids: 向量資料庫查回來的 ID 列表 (List[int] or None)
        """
        self.param_counter = 0
        self.query_params = {} # 重置參數容器

        # 1. 遞迴生成 WHERE 子句
        where_sql = self._recursive_parse(plan["raw_logic_tree"])
        
        final_where = []
        if where_sql:
            final_where.append(where_sql)

        # 2. 注入向量搜尋結果 (Hybrid Join)
        if plan["vector_needed"]:
            if vector_result_ids:
                ids_str = ",".join(str(int(x)) for x in vector_result_ids)
                final_where.append(f"p.id IN ({ids_str})")
            else:
                # 需要向量但沒結果 -> 查無資料
                final_where.append("1=0")

        # 3. 組裝 SQL
        sql = "SELECT " + ", ".join(plan["select_fields"])
        sql += """ FROM all_places p
                   LEFT JOIN place_merchant_category pmc ON p.id = pmc.place_id
                   LEFT JOIN merchant_category mc ON pmc.merchant_category_id = mc.category_id
                   LEFT JOIN place_tags pt ON p.id = pt.place_id
                   LEFT JOIN tags_overview tow ON pt.tag_id = tow.tag_id """
        
        if final_where:
            sql += " WHERE " + " AND ".join(final_where)
            
        sql += " GROUP BY p.id"

        if plan["sort_clauses"]:
            sql += " ORDER BY " + ", ".join(plan["sort_clauses"])

        return sql, self.query_params

    def _recursive_parse(self, node):
        if not node: return None

        # 處理邏輯群組 (AND/OR)
        if "op" in node and "conditions" in node:
            operator = node["op"].upper()
            child_sqls = []
            for child in node["conditions"]:
                child_sql = self._recursive_parse(child)
                if child_sql:
                    child_sqls.append(child_sql)
            
            if not child_sqls: return None

            # ---【修正重點開始】---
            # 如果只有一個條件，直接回傳，不用加括號
            if len(child_sqls) == 1:
                return child_sqls[0]

            # 正確的 SQL 拼接：把 AND/OR 放在中間
            separator = f" {operator} "  # 變成 " AND "
            return f"({separator.join(child_sqls)})"

            


        # 處理單一條件
        key = list(node.keys())[0]
        
        # 如果是 SQL 欄位 -> 生成 SQL
        if key in self.sql_where_mapping:
            db_col = self.sql_where_mapping[key]
            val = node[key]["value"]
            cmp = node[key]["cmp"]
            
            p_name = f"p{self.param_counter}"
            self.query_params[p_name] = val
            self.param_counter += 1
            return f"{db_col} {cmp} %({p_name})s"
        
        # 如果是向量欄位 -> 在 SQL 生成階段直接忽略 (回傳 None)
        # 因為向量邏輯已經在 build_sql 的最外層透過 ID IN (...) 處理了
        elif key in self.vector_fields:
            return None
            
        return None