def generate_hybrid_sql_v1(json_input):
    # RDBMS的標籤映射
    field_mapping = {
        "id": "p.id",
        "name": "p.name",
        "address": "p.address",
        "rating": "p.rating",
        "service_tags": "GROUP_CONCAT(tow.tag_content) AS service_tags",
        "merchant_category": "GROUP_CONCAT(mc.name) AS merchant_categories"
    }
    # 動態加入想知資訊(["info_needed"])的內容
    # 決定SELECT要哪些欄位
    # 檢查 JSON 裡的 info_needed 欄位（使用者還想知道什麼？）
    # .get(..., []): 防呆機制
    select_fields = ["p.id", "p.name", "p.address", "p.rating"]
    for info in json_input.get("info_needed", []):
        # 如果使用者要的資訊在我們的對照表裡
        # 且這個欄位還沒被加進去過
        if info in field_mapping and field_mapping[info] not in select_fields:
            # select_fields.append(...): 就把對應的 SQL 寫法加進 SELECT 清單中
            select_fields.append(field_mapping[info])

    # WHERE 條件映射與變數初始化
    sql_where_mapping = {
        "address": "p.address",
        "merchant_category": "mc.name",
        "service_tags": "tow.tag_content", # 支援標籤過濾
        "rating": "p.rating"
    }
    # 向量資料庫支援的欄位查詢
    vector_fields = ["cuisine_type", "flavor"]
    
    vector_result_ids = None
    has_vector = False
    where_clauses = []
    query_params = {}

    logic = json_input.get("logic_tree", {})
    conditions = logic.get("conditions", [])

    # 條件加入
    for i, cond in enumerate(conditions):
        key = list(cond.keys())[0]
        val = cond[key]["value"]
        cmp_op = cond[key]["cmp"]
    # 接下來需要判斷 key 是否在 sql_where_mapping 裡，如果是，就要組裝成 p.rating >= 4.5 這樣的字串放入 where_clauses。

    # 判斷是否為 SQL 支援的欄位 (例如: rating, address)
    if key in sql_where_mapping:
        db_column = sql_where_mapping[key]
        
        # 簡單的型別判斷：如果是字串，SQL 語法需要加單引號
        # (注意：正式環境建議用參數化查詢 query_params 來防止 SQL Injection)
        if isinstance(val, str):
            clause = f"{db_column} {cmp_op} '{val}'" 
        else:
            clause = f"{db_column} {cmp_op} {val}"
            
        where_clauses.append(clause)

    # 判斷是否為向量欄位 (例如: cuisine_type, flavor)
    elif key in vector_fields:
        # 如果條件涉及向量欄位，我們標記 has_vector 為 True
        # 這會觸發下方的 if has_vector: 邏輯，去限制 ID 範圍
        has_vector = True
        
        # 注意：這裡通常還需要一段程式碼去呼叫 Vector DB
        # 取得 vector_result_ids，這邊假設外部已經處理好或稍後處理

    # 處理向量搜尋結果Hybrid Logic
    if has_vector:
        if vector_result_ids:
            ids_str = ",".join(map(str, vector_result_ids))
            where_clauses.append(f"p.id IN ({ids_str})")
        else:
            where_clauses.append("1=0")

    # 組裝主 SQL 語句
    sql = "SELECT " + ", ".join(select_fields)
    sql += """ FROM all_places p
               LEFT JOIN place_merchant_category pmc ON p.id = pmc.place_id
               LEFT JOIN merchant_category mc ON pmc.merchant_category_id = mc.category_id
               LEFT JOIN place_tags pt ON p.id = pt.place_id
               LEFT JOIN tags_overview tow ON pt.tag_id = tow.tag_id """
    # 組裝 WHERE 與 GROUP BY
    if where_clauses:
        sql += " WHERE " + " AND ".join(where_clauses)

    sql += " GROUP BY p.id"

    # 排序邏輯
    sort_conds = json_input.get("sort_conditions", [])
    if sort_conds:
        sort_clauses = []
        for s in sort_conds:
             sort_clauses.append(f"p.{s['field']} {s['method']}")
        sql += " ORDER BY " + ", ".join(sort_clauses)

    return sql, query_params

def generate_hybrid_sql_v2(json_input):
    # 1. 定義映射 (Mapping)
    field_mapping = {
        "id": "p.id", "name": "p.name", "address": "p.address", "rating": "p.rating",
        "service_tags": "GROUP_CONCAT(tow.tag_content)",
        "merchant_category": "GROUP_CONCAT(mc.name)"
    }
    
    sql_where_mapping = {
        "address": "p.address",
        "merchant_category": "mc.name", 
        "service_tags": "tow.tag_content", 
        "rating": "p.rating"
    }
    
    vector_fields = {"cuisine_type", "flavor"} # 用 Set 搜尋比較快

    # 2. 決定 SELECT 欄位
    select_fields = ["p.id", "p.name", "p.address", "p.rating"]
    for info in json_input.get("info_needed", []):
        if info in field_mapping and field_mapping[info] not in select_fields:
            # 這裡要注意如果是 GROUP_CONCAT 需加上 AS 別名，這裡簡化處理
            select_fields.append(f"{field_mapping[info]} AS {info}")

    # 狀態變數
    has_vector = False
    query_params = {}
    param_counter = 0 # 用來生成獨立的參數名稱 (p0, p1, p2...)

    # ==========================================
    # 3. 核心優化：遞迴解析函式 (Recursive Parser)
    # ==========================================
    def parse_logic_node(node):
        nonlocal has_vector, param_counter
        
        # A. 判斷是否為邏輯群組 (AND/OR)
        if "op" in node and "conditions" in node:
            operator = node["op"].upper() # AND / OR
            child_sqls = []
            
            for child in node["conditions"]:
                child_sql = parse_logic_node(child) # <--- 遞迴呼叫自己
                if child_sql:
                    child_sqls.append(child_sql)
            
            if not child_sqls:
                return None
            
            # 用括號包起來，例如 (A=1 OR B=2)
            return f"({' ' + operator + ' '.join(child_sqls)})"

        # B. 處理葉節點 (單一條件)
        # node 格式預期為: {"rating": {"cmp": ">", "value": 4.5}}
        key = list(node.keys())[0]
        details = node[key]
        
        # 情況 1: 這是 SQL 欄位
        if key in sql_where_mapping:
            db_col = sql_where_mapping[key]
            cmp = details["cmp"]
            val = details["value"]
            
            # 使用參數化查詢 (防止 SQL Injection)
            param_name = f"param_{param_counter}"
            query_params[param_name] = val
            param_counter += 1
            
            return f"{db_col} {cmp} %({param_name})s" # Python DB-API 格式
            
        # 情況 2: 這是向量欄位
        elif key in vector_fields:
            has_vector = True
            return None # 向量條件不產生 SQL WHERE，而是影響外部 filter
            
        return None

    # ==========================================
    
    # 4. 開始解析
    logic_tree = json_input.get("logic_tree", {})
    # 如果根節點就是 op='AND'，直接丟進去解析
    # 如果根節點只是單一條件，也可以包裝後解析，或直接解析
    # 這裡假設 logic_tree 本身就是一個條件或群組
    if not logic_tree:
        where_sql = ""
    else:
        # 有時候 logic_tree 最外層可能沒有 op，視你的 JSON 結構而定
        # 這裡假設最外層有 op，或者它就是一個 condition list
        if "op" not in logic_tree and "conditions" in logic_tree:
             # 容錯處理：如果最外層漏了 op，預設為 AND
             logic_tree["op"] = "AND"
             
        where_sql = parse_logic_node(logic_tree)

    # 5. 處理 Hybrid Vector Logic
    # 這裡假設 vector_result_ids 是從外部向量資料庫查回來的
    vector_result_ids = json_input.get("vector_results") # 假設這裡傳入
    
    final_where = []
    if where_sql:
        final_where.append(where_sql)
        
    if has_vector:
        if vector_result_ids:
            # 注意：這裡不能用參數化，因為 IN (...) 比較特殊，通常直接組字串
            # 但要確保 ids 是整數以策安全
            ids_str = ",".join(str(int(x)) for x in vector_result_ids)
            final_where.append(f"p.id IN ({ids_str})")
        else:
            final_where.append("1=0") # 向量條件有開啟，但沒查到結果 -> 強制查無資料

    # 6. 組裝最終 SQL
    sql = "SELECT " + ", ".join(select_fields)
    sql += """ FROM all_places p
               LEFT JOIN place_merchant_category pmc ON p.id = pmc.place_id
               LEFT JOIN merchant_category mc ON pmc.merchant_category_id = mc.category_id
               LEFT JOIN place_tags pt ON p.id = pt.place_id
               LEFT JOIN tags_overview tow ON pt.tag_id = tow.tag_id """
               
    if final_where:
        sql += " WHERE " + " AND ".join(final_where)
        
    sql += " GROUP BY p.id"
    
    # 排序 (同前)
    sort_conds = json_input.get("sort_conditions", [])
    if sort_conds:
        sort_clauses = [f"p.{s['field']} {s['method']}" for s in sort_conds]
        sql += " ORDER BY " + ", ".join(sort_clauses)

    return sql, query_params