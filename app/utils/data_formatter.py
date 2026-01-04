# app/utils/data_formatter.py
import json
from app.config import Config # 引入 Config 來讀取 base_url 

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

import json

import json

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

def format_response_data(results, plan):
    """
    根據 HybridSQLBuilder 產出的 plan，動態決定要執行的後處理步驟。
    """
    # 取得計畫中標記的需求
    needed_fields = plan.get("select_fields", [])
    photos_needed = plan.get("photos_needed", False)
    distance_needed = plan.get("distance_needed", False)
    
    # 1. 解析 JSON 欄位 (根據 SQL 欄位別名判斷)
    # 檢查 plan 中的 select_fields 字串清單，判斷是否有對應欄位
    parse_targets = []
    if any("AS opening_hours" in f for f in needed_fields):
        parse_targets.append("opening_hours")
    if any("AS facility_tags" in f for f in needed_fields):
        parse_targets.append("facility_tags")
        
    if parse_targets:
        results = parse_json_fields(results, fields_to_parse=parse_targets)
    
    # 2. 格式化設施標籤 (只有 SQL 有選該欄位時才執行)
    if any("AS facility_tags" in f for f in needed_fields):
        from app.utils.format_facility_tags import format_facility_tags
        results = format_facility_tags(results)
    
    # 3. 處理距離顯示
    if distance_needed:
        results = format_distance_display(results)
        
    # 4. 補上照片 (依據 plan 決定)
    if photos_needed:
        from app.utils.get_photo import enrich_results_with_photos
        results = enrich_results_with_photos(results, plan)
        
    return results

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


def check_search_status(db_results, plan):
    """
    檢查搜尋結果狀態並回傳給 AI 參考的旗標
    """
    has_results = len(db_results) > 0
    
    # 判斷是否為「不完整的搜尋」
    # 如果 plan 裡面有 vector_needed 但目前系統尚未支援，這就是不完整搜尋
    is_incomplete = plan.get("vector_needed", False) 
    
    status_info = {
        "no_results_found": not has_results,
        "is_incomplete_search": is_incomplete,
        "suggestion": ""
    }
    
    # 根據結果給予 AI 建議
    if not has_results:
        if is_incomplete:
            status_info["suggestion"] = "找不到符合精確條件的店家。由於語意搜尋尚未開啟，建議放寬標籤或名稱限制。"
        else:
            status_info["suggestion"] = "目前沒有符合所有條件的店家，建議修改關鍵字或過濾條件。"
            
    return status_info