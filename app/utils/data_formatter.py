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

def parse_json_fields(results, fields_to_parse=None):
    """
    通用工具：將結果中的特定欄位從 JSON 字串轉為 Python 物件
    :param results: 資料庫查詢結果 List[Dict]
    :param fields_to_parse: 要解析的欄位名稱列表，預設為 ['opening_hours']
    """
    if fields_to_parse is None:
        fields_to_parse = ['opening_hours']

    for row in results:
        for field in fields_to_parse:
            # 檢查欄位是否存在且有值
            if field in row and row[field]:
                val = row[field]
                # 只有當它是「字串」時才需要解析
                if isinstance(val, str):
                    try:
                        row[field] = json.loads(val)
                    except Exception:
                        pass
    
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