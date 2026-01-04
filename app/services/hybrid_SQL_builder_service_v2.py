import json
from app.utils.distance_utils import get_haversine_distance_sql # 匯入距離計算的SQL生成器
import logging

class HybridSQLBuilder:
    def __init__(self):
        #  定義靜態的映射表 
        # 用於SELECT子句
        self.field_mapping = {
            "id": "p.id", 
            "name": "p.name", 
            "address": "p.address", 
            "rating": "p.rating",
            "phone": "p.phone",       
            "website": "p.website",
            "opening_hours": "p.opening_hours",
            "food_type": "pa.food_type",
            "cuisine_type": "pa.cuisine_type",
            "merchant_categories": "pa.merchant_categories",
            "facility_tags": "pa.facility_tags",
            "lat": "p.lat",
            "lng": "p.lng"
        }
        # 用於where子句
        # 如何篩選資料
        # 這裡必須對應到原始資料表的欄位
        # sql的執行順序是 where -> gourpby -> select
        self.sql_where_mapping = {
            "id": "p.id",
            "name": "p.name",         
            "phone": "p.phone",       
            "website": "p.website",   
            "food_type": "pa.food_type",
            "opening_hours": "p.opening_hours",
            "address": "p.address", 
            "merchant_categories": "pa.merchant_categories",
            "rating": "p.rating"
        }
        # 定義哪些欄位屬於語意搜尋或模糊比對的範疇
        # 這裡的欄位是匯到向量資料庫去搜尋的欄位
        self.vector_fields = { "flavor", "review_summary"}
        self.facility_keys = {
        "內用", "冷氣", "外帶", "吃到飽", "特約停車場", 
        "行動支付", "現金支付", "信用卡" 
        }
        self.json_field_source = "pa.facility_tags"

    # 只負責看懂 JSON，告訴你需不需要跑向量搜尋
    # 解析意圖
    # 回傳一個字典,包含SQL所需的結構以及向量搜尋的需求
    def analyze_intent(self, json_input):
        logging.info("[SQL Builder] 開始解析使用者意圖 (analyze_intent)")
        
        plan = {
            "select_fields": [], # 預設一定查店家的id,name,address,rating欄位
            "sort_clauses": [],      # 存放 ORDER BY 的字串
            "sql_where_logic": None, # 這裡只存邏輯樹結構，還不生成 SQL 字串
            "query_params": {},      # 預留給參數化查詢的字典  
            "vector_needed": False,  # 旗標：是否需要去查向量資料庫
            "vector_keywords": [],    # 若需要，要查哪些關鍵字
            "photos_needed": False, # 是否有photo需求
            "distance_needed": False,
            "user_location": None
        }
        # 獲取使用者的經緯度
        user_loc = json_input.get("user_location")
        # 如果有使用者的座標位置
        if user_loc and "lat" in user_loc and "lng" in user_loc:
            plan["distance_needed"] = True
            plan["user_location"] = user_loc
            logging.debug(f"[SQL Builder] 偵測到使用者座標: {user_loc}，開啟距離計算功能")

        # 取得意圖
        intent = json_input.get("main_intent", "query")
        logging.info(f"[SQL Builder] 主意圖模式: {intent}")

        # 如果意圖的值為"recommend""
        if intent == "recommend":
            logging.info("[SQL Builder] 進入推薦模式: 全選欄位並強制開啟照片")
            # 推main_intent如果等於("recommand")無視info_needed,直接選擇所有欄位
            for key, db_col in self.field_mapping.items():
                plan["select_fields"].append(f"{db_col} AS {key}")

            # 推薦模式強制開啟照片提供功能
            plan["photos_needed"] = True
        
        else:
            # query一般查詢模式
            default_fields = ["id", "name", "address", "rating"]
            for f in default_fields:
                if f in self.field_mapping:
                    plan["select_fields"].append(f"{self.field_mapping[f]} AS {f}")

            # 加入使用者在 info_needed 指定的額外欄位
            for info in json_input.get("info_needed",[]):
                # 處理照片需求
                if info == "photos":
                    plan["photos_needed"] = True

                # 處理距離需求
                if info == "distance" and user_loc:
                    # distance是動態生成的
                    continue
                
                # 處理一般欄位
                if info in self.field_mapping:
                    col_sql = f"{self.field_mapping[info]} AS {info}"
                    # 防止重複加入 (例如 name 已經在預設欄位裡了)
                    if col_sql not in plan["select_fields"]:
                        plan["select_fields"].append(col_sql)

                

        # 處理Sort排序規則,包括distance排序問題
        for s in json_input.get("sort_conditions", []):
            field = s['field']
            method = s['method']
            if field == "distance":
                if plan["distance_needed"]:
                    plan["sort_clauses"].append(f"distance {method}") # 不要加p.
                    logging.debug(f"[SQL Builder] 加入距離排序: {method}")
            else:
                # 一般欄位
                plan["sort_clauses"].append(f"p.{field} {method}")
            # 直接組裝排序的子句,通常傳入的json裡面的sort_conditions會是像這樣:
            # ["sort_conditions": [
            #{
                #"field": "distance",
                #"method": "ASC"
                #},
            #]
            # 所以使用append直接組合起來變成""p.rating DESC"
            # 加入倒PLAN的sort_clauses的list裡面就會是order by 子句
            # 如果是 'distance' 排序，通常需要在外部算好距離後再處理，Distance模組還沒有處理!
            # 若要'distance' 排序會sql執行錯誤,原因是資料庫沒有這個欄位
        # 預先掃描邏輯樹，分離 SQL 條件與向量條件
        # 把原始 logic_tree 存下來，在 build_sql 時才遞迴生成
        # 這裡先掃描是否有向量需求
        self._scan_for_vector_intent(json_input.get("logic_tree", {}), plan)
        # 把原始邏輯樹存入 plan，留給第二階段用
        plan["raw_logic_tree"] = json_input.get("logic_tree", {})
        
        return plan
    

    # 遞迴掃描邏輯樹，看看有沒有向量欄位
    def _scan_for_vector_intent(self, node, plan):
        
        # 這是一個邏輯群組節點,包含 AND/OR 和 conditions 列表
        if not node: return
        # 如果 有conditions節點代表就有下一層的節點
        if "conditions" in node:
            for child in node["conditions"]:
                # 遞迴檢查每一個子條件
                self._scan_for_vector_intent(child, plan)
        else:
            # 這是葉節點 (Leaf Node)，也就是實際的過濾條件
            # 取得欄位名稱 (例如 "flavor")並放入list容器
            key = list(node.keys())[0]

            # 檢查這個欄位是否屬於向量搜尋單位
            # __init__定義的向量搜尋欄位
            if key in self.vector_fields:
                plan["vector_needed"] = True  # 把向量意圖標記為true
                plan["vector_keywords"].append(node[key]["value"]) # 記錄關鍵字，例如 "辣", "日式"
                logging.info(f"[SQL Builder] 發現向量搜尋關鍵字: {key} = {node[key]['value']}")

    # 負責將邏輯樹轉成sql字串
    # 會接收關鍵參數 vector_result_ids:這是向量資料庫搜尋完後回傳的Place id列表
    # 就是已經跑完向量搜尋了現在要生成到MySQL查詢店家的基本訊息
    def build_sql(self, plan, vector_result_ids=None):
        logging.info("[SQL Builder] 開始建構 SQL (build_sql)")
        
        self.param_counter = 0  # 用於生成唯一的參數名稱(p0, p1, p2...)
        self.query_params = {} # 存放參數化查詢的實際值,防止 SQL注入攻擊

        # 遞迴生成 SQL 的 WHERE 子句(處理傳統欄位)
        # 呼叫 _recursive_parse 把邏輯樹轉成字串(例如 "p.rating > 4.0")
        # 這裡一樣還沒有處理距離的處理邏輯!
        where_sql = self._recursive_parse(plan["raw_logic_tree"])
        # 當 self._recursive_parse(...) 執行結束時，遞迴已經跑完了
        # 它吐出了一個巨大的、完整的字串，存進變數 where_sql 裡
        final_where = []
        if where_sql:
            final_where.append(where_sql)

        # 寫入向量搜尋結果
        # 如果plan裡面的vector_needed為true,需要向量搜尋
        if plan["vector_needed"]:
            if vector_result_ids is not None: # 明確檢查是否有傳入列表 (包含空列表)
                if len(vector_result_ids) > 0:
                    # 將 ID 列表轉成字串，例如 [1, 2, 3] -> "1,2,3"
                    
                    ids_str = ",".join(str(int(x)) for x in vector_result_ids)
                    # 生成SQL過濾條件：只選出這些 ID 的店家
                    # 這些id是從向量資料庫搜尋完符合模糊搜索條件的店家id
                    # 這些店家id是要用來下一步到MySQL查詢店家資訊用的
                    final_where.append(f"p.id IN ({ids_str})")
                    logging.info(f"[SQL Builder] 注入向量搜尋結果 ID: {len(vector_result_ids)} 筆")
                else:
                    # 需要向量搜尋但沒結果 -> 查無資料
                    # 這時候SQL回傳空，所以加上 "1=0" (永遠為假)
                    final_where.append("1=0")
                    logging.warning("[SQL Builder] 向量搜尋無結果，強制 SQL 回傳空")
            else:
                # 如果 vector_result_ids 是 None (代表跳過向量步驟)
                # 就不加入任何關於 id IN (...) 的條件，讓 SQL 根據傳統欄位全量搜尋
                logging.info("[SQL Builder] 向量搜尋被跳過或未就緒，不進行 ID 過濾")

        # 計算距離,注入SQL公式
        if plan["distance_needed"] and plan["user_location"]:
            u_lat = plan["user_location"]["lat"]
            u_lng = plan["user_location"]["lng"]
            dist_sql = get_haversine_distance_sql(u_lat, u_lng) # 呼叫 utils 生成公式
            plan["select_fields"].append(f"{dist_sql} AS distance") # 加入select 欄位
            logging.debug("[SQL Builder] 已注入 Haversine 距離計算公式")

        # 組裝 SQL
        # 先組裝select子句
        # all_places (主表)
        # -> place_merchant_category (中間表) -> merchant_category (分類表)
        # -> place_tags (中間表) -> tags_overview (標籤表)
        # 使用 LEFT JOIN 是為了避免因為沒有標籤或分類而導致店家被濾掉。
        # 目前是先寫死的,後續會再想想看有沒有更好的處理方式
        sql = "SELECT " + ", ".join(plan["select_fields"])
        # 修正：在 FROM 與 JOIN 關鍵字前後加入明確的空格
        sql += " FROM all_places p "
        sql += " LEFT JOIN Place_Attributes as pa ON p.id = pa.place_id"
        
        # 如果有 WHERE 條件，把它們用 AND 串起來
        if final_where:
            sql += " WHERE " + " AND ".join(final_where)
        
        # 加上 GROUP BY p.id
        # 因為用了 JOIN (一對多) 和 GROUP_CONCAT (聚合),
        # 必須依據店家 ID 分組，才能將多個標籤縮成一行
        sql += " GROUP BY p.id "

        # 加上排序
        # 還未處理如果有距離排序需求的情況!
        if plan["sort_clauses"]:
            sql += " ORDER BY " + ", ".join(plan["sort_clauses"])

        logging.debug(f"[SQL Builder] 生成 SQL:\n{sql}")
        logging.debug(f"[SQL Builder] 參數: {self.query_params}")

        # 回傳 SQL 字串與參數字典
        return sql, self.query_params

    # 將巢狀JSON邏輯樹轉平為SQL WHERE字串
    def _recursive_parse(self, node):
        if not node: 
            logging.debug("[SQL Builder Debug] 節點為空，跳過解析")
            return None

        # 1. 處理邏輯運算子節點 (AND/OR)
        if "op" in node and "conditions" in node:
            operator = node["op"].upper()
            logging.debug(f"[SQL Builder Debug] 解析群組節點: {operator}, 子條件數: {len(node['conditions'])}")
            child_sqls = []
            for i, child in enumerate(node["conditions"]):
                child_sql = self._recursive_parse(child)
                if child_sql:
                    child_sqls.append(child_sql)
                else:
                    logging.debug(f"[SQL Builder Debug] 群組 {operator} 的第 {i} 個子條件解析結果為空")
            
            if not child_sqls: 
                logging.debug(f"[SQL Builder Debug] 群組 {operator} 無任何有效子條件")
                return None
                
            if len(child_sqls) == 1: 
                return child_sqls[0]
            
            separator = f" {operator} "  
            combined_sql = f"({separator.join(child_sqls)})"
            logging.debug(f"[SQL Builder Debug] 組合群組 SQL: {combined_sql}")
            return combined_sql

        # 2. 處理單一條件 (葉節點)
        # 取得當前條件的 Key (例如: "外帶" 或 "food_type")
        key = list(node.keys())[0]
        node_data = node[key]
        val = node_data.get("value")
        cmp = node_data.get("cmp", "=").upper()
        
        # --- [核心追蹤] ---
        logging.info(f"===> [Recursive Parse] 處理欄位: '{key}' | 算符: {cmp} | 原始值: {val}")

        # 優先檢查向量欄位
        if key in self.vector_fields:
            logging.info(f"[SQL Builder Debug] '{key}' 判定為向量欄位，排除於 SQL 之外")
            return None

        # --- 處理 JSON 設施標籤 ---
        if key in self.facility_keys:
            if val is not True: 
                logging.info(f"[SQL Builder Debug] 設施標籤 '{key}' 值為 {val} (非 True)，略過此條件")
                return None
            
            p_name = f"p{self.param_counter}"
            # 寬鬆匹配邏輯：%"外帶"%true%
            param_value = f'%"{key}"%true%' 
            self.query_params[p_name] = param_value
            self.param_counter += 1
            
            sql_fragment = f"{self.json_field_source} LIKE %({p_name})s"
            logging.debug(f"[SQL Builder Debug] 生成標籤 SQL: {sql_fragment} | 參數 {p_name}: {param_value}")
            return sql_fragment
        
        # --- 處理一般 SQL 欄位 ---
        if key in self.sql_where_mapping:
            db_col = self.sql_where_mapping[key]
            p_name = f"p{self.param_counter}"
            
            if key == "food_type" or cmp == "LIKE":
                param_value = f"%{val}%"
                self.query_params[p_name] = param_value
                self.param_counter += 1
                sql_fragment = f"{db_col} LIKE %({p_name})s"
            else:
                param_value = val
                self.query_params[p_name] = param_value
                self.param_counter += 1
                sql_fragment = f"{db_col} {cmp} %({p_name})s"
                
            logging.debug(f"[SQL Builder Debug] 生成一般欄位 SQL: {sql_fragment} | 參數 {p_name}: {param_value}")
            return sql_fragment
        
        # --- [警告] 欄位未定義 ---
        logging.warning(f"!!! [SQL Builder Warning] 欄位 '{key}' 找不到對應的 Mapping 配置，該條件被丟棄")
        return None