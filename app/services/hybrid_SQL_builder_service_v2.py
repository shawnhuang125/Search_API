import json

class HybridSQLBuilder:
    def __init__(self):
        #  定義靜態的映射表 
        # 用於SELECT子句
        self.field_mapping = {
            "id": "p.id", "name": "p.name", "address": "p.address", "rating": "p.rating",
            "service_tags": "GROUP_CONCAT(tow.tag_content)",
            "merchant_category": "GROUP_CONCAT(mc.name)" 
            # 用GROUP_CONCAT是因為一個地點可能會有很多的merchant_category/service_tags的值
            # 所以要合併成一個字串欄位回傳
        }
        # 用於where子句
        # 如何篩選資料
        # 這裡必須對應到原始資料表的欄位
        # sql的執行順序是 where -> gourpby -> select
        self.sql_where_mapping = {
            "address": "p.address", "merchant_category": "mc.name", 
            "service_tags": "tow.tag_content", "rating": "p.rating"
        }
        # 定義哪些欄位屬於語意搜尋或模糊比對的範疇
        # 這裡的欄位是匯到向量資料庫去搜尋的欄位
        self.vector_fields = {"cuisine_type", "flavor","food_type"}

    # 只負責看懂 JSON，告訴你需不需要跑向量搜尋
    # 解析意圖
    # 回傳一個字典,包含SQL所需的結構以及向量搜尋的需求
    def analyze_intent(self, json_input):
        
        plan = {
            "select_fields": ["p.id", "p.name", "p.address", "p.rating"], # 預設一定查店家的id,name,address,rating欄位
            "sort_clauses": [],      # 存放 ORDER BY 的字串
            "sql_where_logic": None, # 這裡只存邏輯樹結構，還不生成 SQL 字串
            "query_params": {},      # 預留給參數化查詢的字典  
            "vector_needed": False,  # 旗標：是否需要去查向量資料庫
            "vector_keywords": [],    # 若需要，要查哪些關鍵字
            "photos_needed": False # 是否有photo需求
        }

        # 處理 Select子句的欄位,使用者要什麼樣的資訊,從info_needed來的資訊
        # 會檢查 傳入的json裡面的info_needed key的value
        # 然後把info_needed的值(字串)都加到plan的select_fields的list裡面
        for info in json_input.get("info_needed", []):
            # photo的處理,如果有photo需求的話,將photos_needed設為true
            if info == "photos":
                plan["photos_needed"] = True
                continue
            # 一般欄位處理
            # 如果這個欄位在我們的 mapping 表中有定義，且還沒被加進去
            if info in self.field_mapping and self.field_mapping[info] not in plan["select_fields"]:
                # 轉換成 SQL 語法，例如 "p.name" 變成 "p.name AS name"
                plan["select_fields"].append(f"{self.field_mapping[info]} AS {info}")

        # 處理Sort排序規則
        for s in json_input.get("sort_conditions", []):
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
            plan["sort_clauses"].append(f"p.{s['field']} {s['method']}")

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
                # 把向量意圖標記為true
                plan["vector_needed"] = True
                # 記錄關鍵字，例如 "辣", "日式"
                plan["vector_keywords"].append(node[key]["value"])

    # 負責將邏輯樹轉成sql字串
    # 會接收關鍵參數 vector_result_ids:這是向量資料庫搜尋完後回傳的Place id列表
    # 就是已經跑完向量搜尋了現在要生成到MySQL查詢店家的基本訊息
    def build_sql(self, plan, vector_result_ids=None):
        
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
            if vector_result_ids:
                # 將 ID 列表轉成字串，例如 [1, 2, 3] -> "1,2,3"
                ids_str = ",".join(str(int(x)) for x in vector_result_ids)
                # 生成SQL過濾條件：只選出這些 ID 的店家
                # 這些id是從向量資料庫搜尋完符合模糊搜索條件的店家id
                # 這些店家id是要用來下一步到MySQL查詢店家資訊用的
                final_where.append(f"p.id IN ({ids_str})")
            else:
                # 需要向量搜尋但沒結果 -> 查無資料
                # 這時候SQL回傳空，所以加上 "1=0" (永遠為假)
                final_where.append("1=0")

        # 3. 組裝 SQL
        # 先組裝select子句
        sql = "SELECT " + ", ".join(plan["select_fields"])
        # all_places (主表)
        # -> place_merchant_category (中間表) -> merchant_category (分類表)
        # -> place_tags (中間表) -> tags_overview (標籤表)
        # 使用 LEFT JOIN 是為了避免因為沒有標籤或分類而導致店家被濾掉。
        # 目前是先寫死的,後續會再想想看有沒有更好的處理方式
        sql += """ FROM all_places p
                   LEFT JOIN place_merchant_category pmc ON p.id = pmc.place_id
                   LEFT JOIN merchant_category mc ON pmc.merchant_category_id = mc.category_id
                   LEFT JOIN place_tags pt ON p.id = pt.place_id
                   LEFT JOIN tags_overview tow ON pt.tag_id = tow.tag_id """
        
        # 如果有 WHERE 條件，把它們用 AND 串起來
        if final_where:
            sql += " WHERE " + " AND ".join(final_where)
        
        # 加上 GROUP BY p.id
        # 因為用了 JOIN (一對多) 和 GROUP_CONCAT (聚合),
        # 必須依據店家 ID 分組，才能將多個標籤縮成一行
        sql += " GROUP BY p.id"

        # 加上排序
        # 還未處理如果有距離排序需求的情況!
        if plan["sort_clauses"]:
            sql += " ORDER BY " + ", ".join(plan["sort_clauses"])

        # 回傳 SQL 字串與參數字典
        return sql, self.query_params

    # 將巢狀JSON邏輯樹轉平為SQL WHERE字串
    def _recursive_parse(self, node):
        # 如果是當前節點是空的就回傳none
        if not node: return None

        # 處理conditions底下的條件列表,每個條件都算是child
        if "op" in node and "conditions" in node:
            operator = node["op"].upper()
            # 用來放條件句的地方
            # 假設JSON邏輯樹:
            # {
                #"op": "OR",
                #"conditions": [
                    #{ "address": { "value": "台北", "cmp": "=" } },  // 子條件 1
                    #{ "rating":  { "value": 4, "cmp": ">" } }        // 子條件 2
                #]
            #}
            # 當 _recursive_parse 跑到這個節點時，迴圈會跑兩次：
            # 第 1 次迴圈 (處理 address): 呼叫 _recursive_parse(子條件1)
            # 函式回傳字串： "p.address = %(p0)s"
            # 程式把它放進籃子：child_sqls = ["p.address = %(p0)s"]
            # 第 2 次迴圈 (處理 rating)
            # 呼叫 _recursive_parse(子條件2)
            # 函式回傳字串： "p.rating > %(p1)s"
            # 程式把它追加進籃子：child_sqls = ["p.address = %(p0)s", "p.rating > %(p1)s"]
            # 迴圈結束後 (組裝)： 現在籃子裡有兩個零件了。程式會看你的 op 是 "OR"，所以執行 .join()：
            # separator = " OR "
            # result = separator.join(child_sqls)
            # 結果變成字串： "p.address = %(p0)s OR p.rating > %(p1)s"
            child_sqls = []
            # 遞迴處理每一個子條件
            for child in node["conditions"]:
                child_sql = self._recursive_parse(child)
                # 如果有子條件回傳None代表它是向量欄位,這裡會自動過濾掉
                # child_sqls的另外一個功能是過濾掉向量條件
                # 假設JSON變成這樣(SQL 條件 + 向量條件)
                #{
                    #"op": "AND",
                    #"conditions": [
                        #{ "address": { "value": "台北", ... } },   // SQL 欄位
                        #{ "flavor":  { "value": "辣", ... } }      // 向量欄位 (應該被 SQL 忽略)
                    #]
                #}
                # 執行過程
                # 處理address:回傳 "p.address = '台北'"放入child_sqls
                # 處理flavor
                # 因為flavor 是向量欄位，_recursive_parse 會回傳 None
                # 程式碼有一行if child_sql: (如果是 None 就不要加進去)
                # 結果:flavor 被丟掉了,沒進籃子
                # 最終child_sqls的內容
                # child_sqls=["p.address = '台北'"]
                # 因為len(child_sqls) == 1,程式會直接回傳這個字串,而不加 AND 也不加括號
                if child_sql:
                    child_sqls.append(child_sql)
            # 如果過濾後沒有任何有效SQL條件,例如全部是向量條件,回傳 None
            if not child_sqls: return None


            # 優化SQL結構：如果該層只有一個有效條件,不需要加括號()
            # 例如：不需要寫 (rating > 4),直接寫rating > 4即可
            # 情況 A (if len == 1)：直接回傳,不加括號
            if len(child_sqls) == 1:
                return child_sqls[0]

            # 拼接 SQL：用運算子 (如 " AND ") 連接所有子條件
            separator = f" {operator} "  
            # 其他情況:因為有多個條件串接,為了保護邏輯,必須加括號。
            return f"({separator.join(child_sqls)})"

            


        # 處理單一條件(葉節點)
        key = list(node.keys())[0]
        
        # 如果是 SQL 欄位 -> 生成 SQL
        if key in self.sql_where_mapping:
            db_col = self.sql_where_mapping[key] # 取得真實 DB 欄位名 (如 p.address)
            val = node[key]["value"] # 取得值
            cmp = node[key]["cmp"]   # 取得比較運算子(如 =, >, LIKE)
            # 參數化查詢處理 (Parameterized Query)
            # 生成參數代號，例如 p0, p1
            p_name = f"p{self.param_counter}"
            # 將真實值存入字典，而不是直接拼接到SQL字串中(防止 SQL Injection)
            self.query_params[p_name] = val
            self.param_counter += 1
            return f"{db_col} {cmp} %({p_name})s" # 回傳SQL片段，使用 %(name)s 佔位符
        
        # 如果是 向量欄位 (存在於 vector_fields)
        # 在生成 SQL WHERE 字串時，直接忽略它！
        # 因為這些條件已經在 build_sql 的外層透過 `p.id IN (...)` 處理掉了
        # 這裡回傳 None，會被上面的分支 A 過濾掉。
        elif key in self.vector_fields:
            return None
        # # 未知欄位先忽略
        return None
    
def enrich_results_with_photos(results, plan):
    """
    參數:
      results: SQL 查回來的 List[Dict] 結果，例如 [{'id': 101, 'name': '店A'}, ...]
      plan: analyze_intent 產出的計畫書
    """
    
    # 只有當計畫書說「我需要照片」時才執行
    if not plan.get("photos_needed"):
        return results

    base_url = "http://localhost/images/" # 圖片伺服器前綴

    for row in results:
        store_id = str(row['id'])
        row['photos'] = [] # 初始化照片列表
        
        # 根據你的規則：店家ID + 01~10.jpg
        for i in range(1, 11):
            # zfill(2) 會把 1 變成 "01"
            # 假設 ID 是 101，照片就是 10101.jpg, 10102.jpg...
            photo_name = f"{store_id}{str(i).zfill(2)}.jpg"
            full_url = base_url + photo_name
            row['photos'].append(full_url)
            
    return results