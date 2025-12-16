# /app/utils/get_photo.py
from app.config import Config
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