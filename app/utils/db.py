# app/utils/db.py
import aiomysql
import asyncio
import logging
from app.config import Config

# 全域變數，用於儲存連線池實例與同步鎖
_db_pool = None
_db_lock = asyncio.Lock()

async def get_async_db_pool():
    """
    獲取或初始化非同步資料庫連線池。
    使用 Double-Checked Locking 模式確保併發安全性。
    """
    global _db_pool
    
    # 第一次檢查：若已初始化則直接回傳，避免進入鎖競爭
    if _db_pool is not None:
        return _db_pool

    # 第二次檢查：進入鎖定狀態，確保只有一個協程能執行初始化過程
    async with _db_lock:
        if _db_pool is None:
            try:
                logging.info("[DB Utils] 正在初始化 aiomysql 連線池...")
                _db_pool = await aiomysql.create_pool(
                    host=Config.DB_HOST,
                    port=Config.DB_PORT,
                    user=Config.DB_USER,
                    password=Config.DB_PASSWORD,
                    db=Config.DB_NAME,
                    minsize=5,       # 池中保持的最小連線數
                    maxsize=20,      # 池中允許的最大連線數
                    autocommit=True, # 自動提交事務
                    charset="utf8mb4"
                )
                logging.info("[DB Utils] 連線池初始化成功 (Pre-warmed: 5 connections)")
            except Exception as e:
                logging.error(f"[DB Utils] 連線池初始化失敗: {e}")
                raise e
    return _db_pool

async def close_db_pool():
    """
    在程式關閉時安全釋放連線池資源。
    應在 FastAPI 的 shutdown event 中呼叫。
    """
    global _db_pool
    if _db_pool is not None:
        try:
            logging.info("[DB Utils] 正在關閉資料庫連線池...")
            _db_pool.close()
            await _db_pool.wait_closed()
            _db_pool = None # 重置為 None，確保資源完全回收
            logging.info("[DB Utils] 資料庫連線池已完全關閉")
        except Exception as e:
            logging.error(f"[DB Utils] 關閉連線池時發生錯誤: {e}")
            raise e