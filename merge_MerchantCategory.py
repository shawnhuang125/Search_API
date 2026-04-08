import json
import asyncio
import logging
import tkinter as tk
from tkinter import filedialog
from app.utils.db import get_async_db_pool, close_db_pool

# 設定日誌
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def select_file():
    """開啟檔案選擇器並回傳檔案路徑"""
    root = tk.Tk()
    root.withdraw()  # 隱藏主視窗
    file_path = filedialog.askopenfilename(
        title="請選擇要匯入的 JSON 檔案",
        filetypes=[("JSON files", "*.json")]
    )
    root.destroy()
    return file_path

async def update_merchant_categories():
    # 1. 選擇檔案
    file_path = select_file()
    if not file_path:
        logging.warning("未選擇任何檔案，程式結束。")
        return

    # 2. 讀取 JSON 內容
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        logging.info(f"成功讀取檔案: {file_path}，共有 {len(data)} 筆資料。")
    except Exception as e:
        logging.error(f"讀取 JSON 失敗: {e}")
        return

    # 3. 準備 SQL 更新資料 (格式: [(category, original_id), ...])
    update_params = [
        (item.get('merchant_category'), item.get('original_id'))
        for item in data if item.get('original_id') and item.get('merchant_category')
    ]

    if not update_params:
        logging.warning("JSON 中沒有有效的更新資料。")
        return

    # 4. 執行資料庫更新
    pool = await get_async_db_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            sql = """
                UPDATE Place_Attributes 
                SET merchant_category = %s 
                WHERE place_id = %s
            """
            try:
                logging.info(f"正在更新 {len(update_params)} 筆資料...")
                await cur.executemany(sql, update_params)
                logging.info(f"更新完成！影響列數: {cur.rowcount}")
            except Exception as e:
                logging.error(f"資料庫更新失敗: {e}")

async def main():
    try:
        await update_merchant_categories()
    finally:
        # 確保關閉連線池
        await close_db_pool()

if __name__ == "__main__":
    asyncio.run(main())