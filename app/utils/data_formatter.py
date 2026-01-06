# app/utils/data_formatter.py
import json
from app.config import Config # 引入 Config 來讀取 base_url 
# 
def enrich_results_with_photos(results, plan):
    """
    參數:
      results: SQL 查回來的 List[Dict] 結果
      plan: analyze_intent 產出的計畫書
    """
    # 只有當計畫書說「我需要照片」時才執行
    if not plan.get("photos_needed"):
        return results

    # 建議：未來可以改從 Config 讀取，例如 Config.IMAGE_BASE_URL
    base_url = Config.IMAGES_URL

    for row in results:
        store_id = str(row['id']).zfill(3)
        row['photos'] = [] 
        
        # 根據規則：店家ID + 01~10.jpg
        for i in range(1, 11):
            # 檔名規則：[3位數店家ID][2位數流水號].jpg
            # 例如：00501.jpg, 09910.jpg
            photo_name = f"{store_id}{str(i).zfill(2)}.jpg"
            full_url = base_url + photo_name
            row['photos'].append(full_url)
            
    return results


# 若['opening_hours', 'facility_tags']有反斜線就把反斜線拿掉,否則不做任何動作就回傳
def parse_json_fields(results, fields_to_parse=None):
    if fields_to_parse is None:
        fields_to_parse = ['opening_hours', 'facility_tags']

    for row in results:
        for field in fields_to_parse:
            if field in row and isinstance(row[field], str):
                val = row[field]
                # 移除可能影響解析的反斜線與首尾引號
                cleaned_val = val.replace('\\', '')
                if cleaned_val.startswith('"') and cleaned_val.endswith('"'):
                    cleaned_val = cleaned_val[1:-1]
                
                try:
                    # 關鍵：將字串轉為 dict
                    row[field] = json.loads(cleaned_val)
                except Exception:
                    # 解析失敗時，給予 facility_tags 一個空字典以供後續函式處理
                    row[field] = {} if field == 'facility_tags' else cleaned_val
    return results

# 依照plan裡面去處理距離顯示與補上照片與格式化設施標籤 (只有 SQL 有選該欄位時才執行)
def format_response_data(results, plan):
    """
    根據 HybridSQLBuilder 產出的 plan，動態決定要執行的後處理步驟。
    """
    # 取得計畫中標記的需求
    needed_fields = plan.get("select_fields", [])
    photos_needed = plan.get("photos_needed", False)
    distance_needed = plan.get("distance_needed", False)
    
    # 解析 JSON 欄位 (根據 SQL 欄位別名判斷)
    # 檢查 plan 中的 select_fields 字串清單，判斷是否有對應欄位
    parse_targets = []
    if any("AS opening_hours" in f for f in needed_fields):
        parse_targets.append("opening_hours")
    if any("AS facility_tags" in f for f in needed_fields):
        parse_targets.append("facility_tags")
        
    if parse_targets:
        results = parse_json_fields(results, fields_to_parse=parse_targets)
    
    # 格式化設施標籤 (只有 SQL 有選該欄位時才執行)
    if any("AS facility_tags" in f for f in needed_fields):
        from app.utils.format_facility_tags import format_facility_tags
        results = format_facility_tags(results)
    
    # 處理距離顯示
    if distance_needed:
        results = format_distance_display(results)
        
    # 補上照片 (依據 plan 決定)
    if photos_needed:
        from app.utils.get_photo import enrich_results_with_photos
        results = enrich_results_with_photos(results, plan)
        
    return results

# 距離資料的格式化
def format_distance_display(results):
    """
    將距離欄位 (公尺整數) 格式化為易讀字串
    規則:
    - 大於等於 1000m -> 轉為 km (保留3位小數)
    - 小於 1000m -> 維持 m (整數)
    """
    for row in results:
        # 檢查是否有 distance 欄位 (因為有些查詢可能沒算距離)
        if 'distance' in row and row['distance'] is not None:
            try:
                dist_m = float(row['distance']) # 確保是數字
                
                if dist_m >= 1000:
                    # 超過 1 公里：除以 1000，保留 3 位小數，單位 km
                    # 例如: 1254 -> "1.254 km"
                    row['distance'] = f"{dist_m / 1000:.3f} km"
                else:
                    # 小於 1 公里：取整數，單位 m
                    # 例如: 300 -> "300 m"
                    row['distance'] = f"{int(dist_m)} m"
                    
            except (ValueError, TypeError):
                # 防呆：如果資料庫回傳怪怪的數值，就維持原樣
                pass
                
    return results

def check_search_status(db_results, plan, total_count=0):
    """
    檢查搜尋結果狀態，並整合分頁資訊與查無資料時的診斷建議。
    """
    has_results = len(db_results) > 0
    is_incomplete = plan.get("vector_needed", False) 
    
    # --- [新增] 提取分頁參數 ---
    current_page = plan.get("page", 1)
    page_size = plan.get("page_size", 3)
    
    status_info = {
        "location_info": None,    # 用戶經緯度的設定訊息
        "total_count": total_count,     # 符合條件的總筆數
        "current_page": current_page,   # 目前是第幾分頁
        "page_size": page_size,         # 顯示幕前一頁共有幾筆店家數據
        "no_results_found": not has_results,    # 沒有符合的店家資料就會設為true否則預設default
        "is_incomplete_search": is_incomplete,  # 搜尋是否完整
        "has_next": (current_page * page_size) < total_count,   # 目前累積顯示的筆數是否小於總筆數
        "suggestion": "",       #如果沒有任何符合篩選條件的店家資料的情況下會顯示哪邊出問題
        "debug_details": None  
    }

    if plan.get("distance_needed"):
        loc = plan.get("user_location")
        source = plan.get("location_source")
        
        if source == "default":
            status_info["location_info"] = {
                "type": "default_fallback",
                "message": f"未偵測到您的位置，目前以系統預設點 (崑山科大: {loc['lat']}, {loc['lng']}) 計算距離。",
                "coordinates": loc
            }
        elif source == "user":
            status_info["location_info"] = {
                "type": "user_provided",
                "message": "已根據您提供的位置計算距離。",
                "coordinates": loc
            }
    
    if not has_results:
        active_params = plan.get("query_params", {})
        
        status_info["debug_details"] = {
            "applied_filters": active_params,
            "sql_where_clause": plan.get("generated_where_clause"),
            "vector_search_status": "Not Supported" if is_incomplete else "Not Triggered"
        }

        # 建議邏輯維持原樣，但因應結構化欄位微調
        if is_incomplete:
            status_info["suggestion"] = "找不到符合精確條件的店家。建議放寬標籤或名稱限制。"
        elif active_params:
            # 修改：現在設施標籤是 TINYINT(1) 數值 1，不再是帶引號的字串
            # 檢查是否有任何參數的值是 1，代表有開啟設施過濾
            has_facility = any(v == 1 for v in active_params.values() if isinstance(v, int))
            if has_facility:
                status_info["suggestion"] = "目前設施條件（如：冷氣、內用）組合過於嚴格，建議減少勾選項目。"
            else:
                status_info["suggestion"] = "目前關鍵字搜尋不到店家，請更換關鍵字。"
        else:
            status_info["suggestion"] = "查無資料，建議調整搜尋範圍。"
            
    return status_info