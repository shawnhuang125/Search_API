# app/utils/data_formatter.py
import json
from app.config import Config # 建議：引入 Config 來讀取 base_url (可選)

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
    base_url = "http://localhost/images/" 

    for row in results:
        store_id = str(row['id'])
        row['photos'] = [] 
        
        # 根據規則：店家ID + 01~10.jpg
        for i in range(1, 11):
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