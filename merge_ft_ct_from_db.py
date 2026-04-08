import json
import asyncio
import logging
from app.utils.db import get_async_db_pool, close_db_pool

# 設定日誌等級
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

async def fetch_place_attributes(pool, original_id):
    """
    根據 original_id 查詢資料庫中的 Place_Attributes
    """
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            # SQL 邏輯：根據 id 找對應的標籤
            sql = "SELECT food_type, cuisine_type FROM Place_Attributes WHERE place_id = %s"
            await cur.execute(sql, (original_id,))
            result = await cur.fetchone()
            return result

def format_to_list(value):
    """
    處理資料庫回傳值：
    如果是字串且包含逗號，轉成列表；如果是 None，回傳空列表。
    """
    if not value:
        return []
    if isinstance(value, str):
        # 移除空格並根據逗號或分號分割（視你資料庫存放格式而定）
        return [item.strip() for item in value.replace(';', ',').split(',') if item.strip()]
    return value if isinstance(value, list) else [value]

async def sync_json_with_db(input_file, output_file):
    # 1. 初始化資料庫連線池
    pool = await get_async_db_pool()
    
    try:
        # 2. 載入 JSON 資料
        logging.info(f"讀取檔案: {input_file}")
        with open(input_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        total_count = len(data)
        updated_count = 0

        # 3. 逐一查詢並覆蓋
        logging.info(f"開始同步 {total_count} 筆店家的屬性資料...")
        
        for item in data:
            oid = item.get('original_id')
            if not oid:
                continue

            # 到資料庫抓資料
            db_attr = await fetch_place_attributes(pool, oid)
            
            if db_attr:
                # 覆蓋原本的欄位
                # 這裡使用 format_to_list 確保輸出是 JSON 陣列格式 [ "台式", "麵食" ]
                item['food_type'] = format_to_list(db_attr.get('food_type'))
                item['cuisine_type'] = format_to_list(db_attr.get('cuisine_type'))
                updated_count += 1
            else:
                # 如果資料庫查無此 ID，可以選擇清空或保留
                # item['food_type'] = []
                # item['cuisine_type'] = []
                logging.warning(f"ID {oid} ({item.get('name')}) 在資料庫中找不到屬性")

        # 4. 寫回 JSON 檔案
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        logging.info(f"同步完成！共更新 {updated_count}/{total_count} 筆資料。")
        logging.info(f"結果已儲存至: {output_file}")

    except Exception as e:
        logging.error(f"執行過程中發生錯誤: {e}")
    finally:
        # 5. 務必關閉連線池
        await close_db_pool()

if __name__ == "__main__":
    # 設定你的輸入與輸出檔名
    INPUT_JSON = 'restaurants_20260324_unified.json' 
    OUTPUT_JSON = 'restaurants_20260326_all.json'
    
    asyncio.run(sync_json_with_db(INPUT_JSON, OUTPUT_JSON))