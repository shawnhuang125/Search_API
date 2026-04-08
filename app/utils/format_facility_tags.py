# app/utils/format_facility_tags.py
def format_facility_tags(results):
    for row in results:
        raw_tags = row.get("facility_tags")
        
        # 1. 如果已經是 List (這是你資料庫目前的真實狀況)
        if isinstance(raw_tags, list):
            # 直接保留，不需處理，或者做點過濾
            row["facility_tags"] = raw_tags
            
        # 2. 如果是 Dict (相容舊邏輯或未來可能的變動)
        elif isinstance(raw_tags, dict):
            processed_list = [k for k, v in raw_tags.items() if v is True]
            row["facility_tags"] = processed_list
            
        # 3. 其他情況 (包含 None)
        else:
            row["facility_tags"] = []
            
    return results