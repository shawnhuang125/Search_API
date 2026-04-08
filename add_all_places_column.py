import json
import asyncio
import logging
from decimal import Decimal
from datetime import datetime
from app.utils.db import get_async_db_pool, close_db_pool

# 設定日誌
logging.basicConfig(level=logging.INFO)

class CustomEncoder(json.JSONEncoder):
    """處理 JSON 無法序列化 Decimal 與 datetime 的問題"""
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        if isinstance(obj, datetime):
            return obj.strftime('%Y-%m-%d %H:%M:%S')
        return super(CustomEncoder, self).default(obj)

def rename_level_field(item):
    """
    將欄位 level 改名為 review_labeled_level
    """
    if "level" in item:
        # 使用 pop 取得值並同時刪除舊鍵
        item["review_labeled_level"] = item.pop("level")
    return item

def reorder_payload(item):
    """
    根據指定的順序重新排列字典欄位
    """
    # 注意：這裡的 order 已經將 level 改為 review_labeled_level
    order = [
        "place_id", "google_place_id", "vdb_id", "name", "address", "phone", 
        "website", "map_url", "opening_hours", "rating", "price_level", 
        "user_ratings_total", "business_status", "lat", "lng", "source", 
        "flavor", "food_type", "cuisine_type", "service_tags", "facility_tags", 
        "merchant_category", "review_labeled_level", "review_summary", "review_text", 
        "create_at", "updated_at", "created_by"
    ]
    
    new_item = {}
    for key in order:
        new_item[key] = item.get(key, None)
            
    # 補上不在 order 中的其他欄位
    for key in item:
        if key not in new_item:
            new_item[key] = item[key]
            
    return new_item

async def enrich_and_format_json(input_file, output_file):
    # 1. 讀取原始 JSON
    try:
        with open(input_file, 'r', encoding='utf-8') as f:
            source_data = json.load(f)
    except Exception as e:
        logging.error(f"讀取檔案失敗: {e}")
        return

    # 2. 獲取資料庫連線
    pool = await get_async_db_pool()
    temp_results = []

    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            for item in source_data:
                # 取得 ID 並改名為 place_id
                raw_id = item.pop("original_id", None) or item.get("place_id")
                
                if raw_id is None:
                    continue
                
                place_id = int(raw_id)
                item["place_id"] = place_id

                # 3. 查詢資料庫
                sql = """
                    SELECT 
                        google_place_id, address, phone, website, map_url, 
                        opening_hours, rating, price_level, user_ratings_total, 
                        business_status, lat, lng, source, create_at, updated_at, created_by
                    FROM all_places 
                    WHERE id = %s
                """
                await cur.execute(sql, (place_id,))
                db_row = await cur.fetchone()

                if db_row:
                    item.update(db_row)
                
                # --- 新增步驟：改名 level 欄位 ---
                item = rename_level_field(item)
                
                temp_results.append(item)

    # 4. 根據 place_id 排序
    temp_results.sort(key=lambda x: x.get("place_id", 0))

    # 5. 按照指定欄位順序重排
    final_results = [reorder_payload(it) for it in temp_results]

    # 6. 寫入檔案
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(final_results, f, ensure_ascii=False, indent=2, cls=CustomEncoder)
        logging.info(f"成功完成！level 已改名並排序輸出至 {output_file}")
    except Exception as e:
        logging.error(f"寫入檔案失敗: {e}")

async def main():
    input_filename = "restaurants_0325_20260326.json" 
    output_filename = "restaurants_20260326_all.json"
    
    await enrich_and_format_json(input_filename, output_filename)
    await close_db_pool()

if __name__ == "__main__":
    asyncio.run(main())