# app/utils/quality_checker.py
def evaluate_search_quality(db_results, vector_search_info, plan):
    """
    評估搜尋品質，並生成對 AI 的行為指示。
    """
    s_id = plan.get("s_id", "unknown")
    
    # 預設狀態
    is_fallback = False
    quality_label = "success"
    ai_hint = "完美匹配用戶意圖"

    # 1. 判斷是否為空結果
    if not db_results:
        return "no_data", True, "完全找不到符合條件的資料，請引導用戶放寬條件"

    # 2. 判斷是否觸發了折衷方案 (保底機制)
    # 狀況 A: 向量搜尋標記為 no_match
    # 狀況 B: 使用者想要向量搜尋，但最後只靠 SQL 保底排序回傳
    if vector_search_info.get("status") == "no_match" or \
       (plan.get("vector_needed") and not vector_search_info.get("details")):
        is_fallback = True
        quality_label = "partial_success"
        ai_hint = "精確匹配失敗，目前回傳的是根據星等或距離的保底推薦，請以『建議』語氣回覆"

    # 3. 判斷結果數量是否過少 (可選，增加 AI 的警覺性)
    if len(db_results) < plan.get("page_size", 3) and not is_fallback:
        ai_hint += "，但結果數量較少，可提示用戶可能還有其他選擇"

    return quality_label, is_fallback, ai_hint