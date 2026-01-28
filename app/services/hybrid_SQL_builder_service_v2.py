import json
from app.utils.distance_utils import get_haversine_distance_sql # 匯入距離計算的SQL生成器
import logging

class HybridSQLBuilder:
    def __init__(self):
        #  定義靜態的映射表 
        # 用於SELECT子句
        # 輸出的JSON內容的鍵值也會照這個映射表生內容
        self.field_mapping = {
            "id": "p.id", 
            "restaurant_name": "p.name", 
            "address": "p.address", 
            "rating": "p.rating",
            "phone": "p.phone",       
            "website": "p.website",
            "opening_hours": "p.opening_hours",
            "user_ratings_total": "p.user_ratings_total",
            #"time": "p.opening_hours",             # 額外支援 time
            "food_type": "pa.food_type",
            "cuisine_type": "pa.cuisine_type",
            #"cuisine": "pa.cuisine_type",          # 額外支援 cuisine
            "merchant_categories": "pa.merchant_categories",
            #"restaurant_type": "pa.merchant_categories", # 依照要求：對應到類別
            "facility_tags": "pa.facility_tags",
            #"service_tags": "pa.facility_tags",    # 依照要求：對應到標籤
            "lat": "p.lat",
            "lng": "p.lng",
            #"dine_in": "pa.has_dine_in",
            #"air_conditioner": "pa.has_air_conditioner",
            #"takeout": "pa.has_takeout",
            #"all_you_can_eat": "pa.is_all_you_can_eat",
            #"private_parking": "pa.has_private_parking",
            #"mobile_payment": "pa.accept_mobile_payment",
            #"cash_only": "pa.accept_cash_payment",
            #"credit_card": "pa.accept_credit_card"
        }
        # 用於where子句
        # 如何篩選資料
        # 這裡必須對應到原始資料表的欄位
        # sql的執行順序是 where -> gourpby -> select
        self.sql_where_mapping = {
            "id": "p.id",
            "restaurant_name": "p.name",         
            "phone": "p.phone",       
            "website": "p.website",   
            "food_type": "pa.food_type",
            "opening_hours": "p.opening_hours",
            "user_ratings_total": "p.user_ratings_total",
            "time": "p.opening_hours",             # 支援 logic_tree 傳入 time
            "address": "p.address", 
            "rating": "p.rating",
            "merchant_categories": "pa.merchant_categories",
            "restaurant_type": "pa.merchant_categories", # 依照要求：對應到類別
            "cuisine": "pa.cuisine_type",          # 支援 logic_tree 傳入 cuisine
            "service_tags": "pa.facility_tags",    # 支援 logic_tree 傳入 service_tags
            
            # --- 設施與標籤映射 (中文 Key 由 AI 產出) ---
            "內用": "pa.has_dine_in",
            "冷氣": "pa.has_air_conditioner",
            "外帶": "pa.has_takeout",
            "吃到飽": "pa.is_all_you_can_eat",
            "特約停車場": "pa.has_private_parking",
            "行動支付": "pa.accept_mobile_payment",
            "現金支付": "pa.accept_cash_payment",
            "信用卡": "pa.accept_credit_card"
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

        s_id = json_input.get("s_id")
        if not s_id:
                    logging.error("[SQL Builder] 請求缺少 s_id，拒絕解析意圖")
                    # 拋出異常，這會被外部的 try-except 捕捉並回傳給前端
                    raise ValueError("Missing s_id: 多用戶環境下必須提供 Session ID 以進行追蹤")
        
        plan = {
            "s_id": s_id,       # 用戶連線id
            "location_source": "none", # 新增：記錄來源 (user / default / none)
            "select_fields": [], # 預設一定查店家的id,name,address,rating欄位
            "sort_clauses": [],      # 存放 ORDER BY 的字串
            "sql_where_logic": None, # 這裡只存邏輯樹結構，還不生成 SQL 字串
            "query_params": {},      # 預留給參數化查詢的字典  
            "page": json_input.get("page", 1),           # 記錄當前頁碼
            "page_size": json_input.get("page_size", 3), # 記錄每頁顯示幾筆
            "vector_needed": False,  # 旗標：是否需要去查向量資料庫
            "vector_keywords": [],    # 若需要，要查哪些關鍵字
            "photos_needed": False, # 是否有photo需求
            "distance_needed": False,
            "user_location": None
        }

        # 獲取使用者的經緯度
        user_loc = json_input.get("user_location")
        # 如果有[info_needed] = 包含distance需求或sort_condition有距離排序
        # 但沒有usder_location就先用預設的經緯度
        wants_distance = (
            "distance" in json_input.get("info_needed", []) or 
            any(s.get("field") == "distance" for s in json_input.get("sort_conditions", []))
        )
        # 設定經位度訊息提供回傳檢查
        if user_loc and "lat" in user_loc and "lng" in user_loc:
            plan["location_source"] = "user" # 使用者提供
            plan["distance_needed"] = True
            plan["user_location"] = user_loc
        elif wants_distance:
            # 注入崑山科大座標
            plan["location_source"] = "default" 
            plan["distance_needed"] = True
            plan["user_location"] = {"lat": 22.9972300, "lng": 120.2522700}
            logging.warning(f"[SQL Builder] 使用預設座標 (崑山科大): {plan['user_location']}")
        
        # 如果沒傳座標但需要距離，則注入預設座標
        if not user_loc or "lat" not in user_loc or "lng" not in user_loc:
            if wants_distance:
                # 暫時寫死台南火車站座標，方便開發測試
                user_loc = {"lat": 22.9972300, "lng": 120.2522700}
                logging.warning(f"[SQL Builder] 未偵測到座標但功能需要距離服務，注入預設座標: {user_loc}")

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
            base_fields = {
                "id": "p.id",
                "restaurant_name": "p.name", # 強制回傳名稱
                "address": "p.address",
                "rating": "p.rating",
                "reviews_count": "p.reviews_count"
            }
            
            for key, db_col in base_fields.items():
                plan["select_fields"].append(f"{db_col} AS {key}")

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
        
        # 1. 初始化分頁變數
        page = plan.get("page", 1)
        page_size = plan.get("page_size", 3)
        offset = (page - 1) * page_size

        # 2. 【關鍵】重置計數器與參數字典，確保每次生成 SQL 都是從 p0 開始
        self.param_counter = 0 
        self.query_params = {} 

        # 3. 遞迴生成 WHERE 子句
        # 產生的參數會存入 self.query_params，計數器會增加
        where_sql = self._recursive_parse(plan["raw_logic_tree"])

        # 將產生的中間結果存回 plan 供除錯與 diagnostics 使用
        plan["generated_where_clause"] = where_sql
        plan["query_params"] = self.query_params

        final_where = []
        if where_sql:
            final_where.append(where_sql)

        # 計算距離公式注入
        if plan.get("distance_needed") and plan.get("user_location"):
            u_lat = plan["user_location"]["lat"]
            u_lng = plan["user_location"]["lng"]
            dist_sql = get_haversine_distance_sql(u_lat, u_lng)
            
            # 防止重複加入 distance 欄位
            dist_alias = f"{dist_sql} AS distance"
            if not any("AS distance" in f for f in plan["select_fields"]):
                plan["select_fields"].append(dist_alias)
                logging.debug("[SQL Builder] 已注入 Haversine 距離計算公式")

        # 6. 組裝最終 SQL
        sql = "SELECT " + ", ".join(plan["select_fields"])
        sql += " FROM all_places p "
        sql += " LEFT JOIN Place_Attributes as pa ON p.id = pa.place_id"
        
        if final_where:
            sql += " WHERE " + " AND ".join(final_where)
        
        # 必須依據 ID 分組以支援聚合欄位
        sql += " GROUP BY p.id "

        # 處理排序
        if plan.get("sort_clauses"):
            sql += " ORDER BY " + ", ".join(plan["sort_clauses"])

        # 加上 LIMIT 與 OFFSET 實現分頁
        sql += f" LIMIT {page_size} OFFSET {offset}"

        logging.debug(f"[SQL Builder] 生成 SQL:\n{sql}")
        return sql, self.query_params

    # 將巢狀JSON邏輯樹轉平為SQL WHERE字串
    def _recursive_parse(self, node):
        if not node: 
            logging.debug("[SQL Builder Debug] 節點為空，跳過解析")
            return None

        # 處理邏輯運算子節點 (AND/OR)
        # 此區塊負責處理帶有子條件列表 (conditions) 的複合邏輯節點
        if "op" in node and "conditions" in node:
            operator = node["op"].upper() # 取得運算子 (如 'and', 'or') 並轉大寫以符合 SQL 標準
            logging.debug(f"[SQL Builder Debug] 解析群組節點: {operator}, 子條件數: {len(node['conditions'])}")
            child_sqls = []
            # 遍歷所有子條件，進行遞迴解析
            for i, child in enumerate(node["conditions"]):
                # 【遞迴呼叫】繼續往深處解析，直到遇到葉節點 (實際的欄位比較)
                child_sql = self._recursive_parse(child)
                # 如果該子條件產生了有效的 SQL 片段 (非向量欄位或空值)，則加入清單
                if child_sql:
                    child_sqls.append(child_sql)
                else:
                    logging.debug(f"[SQL Builder Debug] 群組 {operator} 的第 {i} 個子條件解析結果為空")
            # 安全檢查：如果該群組內所有子條件解析後都沒有結果，則回傳 None 讓上層跳過此群組
            if not child_sqls: 
                logging.debug(f"[SQL Builder Debug] 群組 {operator} 無任何有效子條件")
                return None
            # 優化：如果群組內只有一個有效條件，就不需要額外包覆括號與運算子
            if len(child_sqls) == 1: 
                return child_sqls[0]
            # 使用目前的運算子 (AND/OR) 串接所有子片段，並用括號封裝以確保運算優先權正確
            # 例如: (p.rating > 4.5 OR p.address LIKE '%永康%')
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

        # --- [關鍵修正：統一脫殼] ---
        # 只要 val 是只有一個元素的 list，不管 cmp 是什麼，先把它轉成純字串/數值
        # 這樣後續不論走 IN 還是 LIKE 邏輯，item 都會是乾淨的
        if isinstance(val, list) and len(val) == 1:
            val = val[0]
        
        # 核心追蹤
        logging.info(f"===> [Recursive Parse] 處理欄位: '{key}' | 算符: {cmp} | 原始值: {val}")

        # 優先檢查向量欄位
        if key in self.vector_fields:
            logging.info(f"[SQL Builder Debug] '{key}' 判定為向量欄位，排除於 SQL 之外")
            return None

        # 處理 JSON 設施標籤
        if key in self.facility_keys:
            if val is not True:
                logging.info(f"[SQL Builder Debug] 設施標籤 '{key}' 值為 {val} (非 True)，略過此條件")
                return None
            # 從 sql_where_mapping 取得對應的新欄位名 (如 pa.has_air_conditioner)
            db_col = self.sql_where_mapping.get(key)
            if not db_col: return None
            p_name = f"p{self.param_counter}"
            # 數值改為 1 (TINYINT 1 代表 True)
            self.query_params[p_name] = 1
            self.param_counter += 1
            # 生成精確比對 SQL: "pa.has_air_conditioner = 1"
            sql_fragment = f"{db_col} = %({p_name})s"
            logging.debug(f"[SQL Builder] 生成精確設施 SQL: {sql_fragment}")
            return sql_fragment
        
        # --- 處理一般 SQL 欄位 ---
        if key in self.sql_where_mapping:
            db_col = self.sql_where_mapping[key]
            # 注意：這裡先不要宣告 p_name，交給各分支處理 counter
            
            fields_to_force_like = ["food_type", "restaurant_type", "restaurant_name", "merchant_categories", "address"]

            # 統一脫殼：確保 val 只要是單一元素的 list 就轉成純字串
            safe_val = val[0] if isinstance(val, list) and len(val) == 1 else val

            # 強制模糊比對欄位
            # 只要在名單內，不管 AI 給什麼 cmp，一律強制轉 LIKE
            if key in fields_to_force_like or cmp == "LIKE":
                p_name = f"p{self.param_counter}"
                param_value = f"%{safe_val}%" # 此時 safe_val 已經是 '崑大路'
                self.query_params[p_name] = param_value
                self.param_counter += 1
                sql_fragment = f"{db_col} LIKE %({p_name})s"
                logging.debug(f"[SQL Builder Debug] 生成強制模糊 SQL: {sql_fragment} | {p_name}: {param_value}")
                return sql_fragment

            # 處理真正的集合查詢 (IN)
            elif cmp in ["in", "not in"]:
                val_list = val if isinstance(val, list) else [val]
                p_names = []
                for item in val_list:
                    current_p = f"p{self.param_counter}"
                    self.query_params[current_p] = item
                    p_names.append(f"%({current_p})s")
                    self.param_counter += 1
                param_placeholders = ", ".join(p_names)
                sql_fragment = f"{db_col} {cmp} ({param_placeholders})"
                logging.debug(f"[SQL Builder Debug] 生成集合 SQL: {sql_fragment}")
                return sql_fragment
            
            # 一般精確比對
            else:
                p_name = f"p{self.param_counter}"
                self.query_params[p_name] = safe_val
                self.param_counter += 1
                sql_fragment = f"{db_col} {cmp} %({p_name})s"
                logging.debug(f"[SQL Builder Debug] 生成一般 SQL: {sql_fragment}")
                return sql_fragment
        
        # 欄位未定義
        logging.warning(f"!!! [SQL Builder Warning] 欄位 '{key}' 找不到對應的 Mapping 配置，該條件被丟棄")
        return None
    


    def build_count_sql(self, plan, vector_result_ids=None):
        """
        生成用於計算總筆數的 SQL
        """
        # 確保 Count 查詢從 p0 開始，且不殘留舊參數 ---
        self.param_counter = 0 
        self.query_params = {}

        sql = "SELECT COUNT(DISTINCT p.id) AS total FROM all_places p "
        sql += " LEFT JOIN Place_Attributes as pa ON p.id = pa.place_id"
        
        final_where = []
        # 重新呼叫遞迴解析，這會生成全新的、乾淨的 p0, p1...
        where_sql = self._recursive_parse(plan["raw_logic_tree"])
        if where_sql:
            final_where.append(where_sql)
            
        # 向量 ID 邏輯保持不變
        if plan.get("vector_needed") and vector_result_ids is not None:
            if len(vector_result_ids) > 0:
                ids_str = ",".join(str(int(x)) for x in vector_result_ids)
                final_where.append(f"p.id IN ({ids_str})")
            else:
                final_where.append("1=0")

        if final_where:
            sql += " WHERE " + " AND ".join(final_where)
            
        return sql, self.query_params