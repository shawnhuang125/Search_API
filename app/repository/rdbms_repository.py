# 引入必要的非同步庫
import time
import asyncio
from typing import List, Dict, Any, Tuple 
import logging
import aiomysql  

from app.utils.db import get_async_db_pool 

class RdbmsRepository:
    def __init__(self, use_mock: bool = False):
        logging.info("[RDBMS Repo] 初始化模式: REAL DB (Async)")

    # 這裡加入 s_id 參數，預設為 None 增加相容性
    async def execute_dynamic_query(self, sql: str, params: Dict[str, Any], s_id: str = None) -> Tuple[List[Dict[str, Any]], float]:
        # 調用非同步實作並等待結果
        return await self._execute_real_db(sql, params, s_id)

    async def _execute_real_db(self, sql: str, params: Dict[str, Any], s_id: str = None) -> Tuple[List[Dict[str, Any]], float]:
        connection = None
        start_time = time.time()
        # 建立一個辨識字串，方便 Log 閱讀
        log_prefix = f"[RDBMS Repo][SID: {s_id}]" if s_id else "[RDBMS Repo]"
        
        try:
            pool = await get_async_db_pool()
            async with pool.acquire() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cursor:
                    
                    # 使用 s_id 列印除錯資訊
                    logging.info(f"{log_prefix} SQL 語句: {sql}")
                    logging.info(f"{log_prefix} 綁定參數內容與型別: " + 
                                 ", ".join([f"{k}: {v} ({type(v).__name__})" for k, v in params.items()]))
                    
                    await cursor.execute(sql, params)
                    records = await cursor.fetchall()
                    
                    end_time = time.time()
                    execution_time = end_time - start_time
                    
                    if records:
                        sample = records[0]
                        logging.info(f"{log_prefix} 取得第一筆原始資料範例: {sample}")
                    else:
                        logging.warning(f"{log_prefix} 查詢結果為空，請檢查 SQL 條件或資料庫編碼")
                    
                    logging.info(f"{log_prefix} 查詢成功，取得 {len(records)} 筆資料，耗時: {execution_time:.5f}秒")
                    return list(records), execution_time

        except aiomysql.Error as e:
            logging.error(f"{log_prefix} 資料庫錯誤: {e}")
            return [], 0.0
        except Exception as e:
            logging.error(f"{log_prefix} 系統錯誤: {e}")
            return [], 0.0