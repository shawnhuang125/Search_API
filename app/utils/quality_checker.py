# app/utils/quality_checker.py
def evaluate_search_quality(db_results, vector_search_info, rdb_info, plan):
    # 優先讀取 search_and_rank 埋進來的自定義提示
    # 假設 vector_search_info 就是我們在 VectorService 裡傳回的 info 字典
    custom_status = vector_search_info.get("status")
    custom_hint = vector_search_info.get("message")

    status = rdb_info.get("status")
    if status == "sql_no_data":
        # AI 語氣：道歉並建議放寬硬性條件
        return "no_data", True, "抱歉，目前搜尋範圍內沒有符合您『硬性要求』的店家。建議您可以換個位置或取消部分標籤再試試。"
    
    # 1. 處理 Case 0: 查無資料
    if custom_status == "no_data" or not db_results:
        return "no_data", True, "完全找不到符合條件的資料，請誠實告訴用戶並建議放寬篩選範圍（例如增加搜尋半徑）。"

    # 2. 處理 Case 1: 精確匹配
    if custom_status == "exact_one_match":
        return "success", False, "精確找到唯一匹配的店家，請以肯定的語氣推薦此店家。"

    # 3. 處理 Case N (含保底)
    is_fallback = False
    quality_label = "success"
    ai_hint = "搜尋成功，已找到多筆符合條件的店家。"

    if custom_status == "no_match":
        is_fallback = True
        quality_label = "partial_success"
        ai_hint = "無法找到與描述完全一致的店家，原本的嚴格條件查無結果，已自動為您放寬條件搜尋。"

    return quality_label, is_fallback, ai_hint