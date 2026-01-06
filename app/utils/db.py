# utils/db.py
import aiomysql
import asyncio
import logging
from app.config import Config

# 全域變數，用於儲存連線池實例
_db_pool = None

async def get_async_db_pool():
    """
    獲取或初始化非同步資料庫連線池。
    """
    global _db_pool
    if _db_pool is None:
        try:
            logging.info("[DB Utils] 正在初始化 aiomysql 連線池...")
            _db_pool = await aiomysql.create_pool(
                host=Config.DB_HOST,
                port=Config.DB_PORT,
                user=Config.DB_USER,
                password=Config.DB_PASSWORD,
                db=Config.DB_NAME,
                minsize=5,       # 池中最小連線數
                maxsize=20,      # 池中最大連線數
                autocommit=True,
                charset="utf8mb4",
                cursorclass=aiomysql.DictCursor # 確保回傳字典格式
            )
            logging.info("[DB Utils] 連線池初始化成功")
        except Exception as e:
            logging.error(f"[DB Utils] 連線池初始化失敗: {e}")
            raise e
    return _db_pool

async def close_db_pool():
    """
    在程式關閉時安全釋放連線池。
    """
    global _db_pool
    if _db_pool is not None:
        _db_pool.close()
        await _db_pool.wait_closed()
        logging.info("[DB Utils] 連線池已關閉")