# 1. 引入必要的非同步庫
import time
import asyncio
from typing import List, Dict, Any, Tuple 
import logging
import aiomysql  

from app.utils.db import get_async_db_pool 

class RdbmsRepository:
    def __init__(self, use_mock: bool = False):
        logging.info("[RDBMS Repo] 初始化模式: REAL DB (Async)")

    async def execute_dynamic_query(self, sql: str, params: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], float]:
        # 調用非同步實作並等待結果
        return await self._execute_real_db(sql, params)

    async def _execute_real_db(self, sql: str, params: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], float]:
        connection = None
        start_time = time.time()
        
        try:
            # 獲取非同步連線池
            pool = await get_async_db_pool()
            # 從池中取得連線
            async with pool.acquire() as conn:
                # 建立字典格式的 Cursor (對應原本 pymysql 的預設行為)
                async with conn.cursor(aiomysql.DictCursor) as cursor:
                    
                    # [保留除錯點 1]
                    logging.info(f"[RDBMS Repo Debug] SQL 語句: {sql}")
                    logging.info(f"[RDBMS Repo Debug] 綁定參數內容與型別: " + 
                                 ", ".join([f"{k}: {v} ({type(v).__name__})" for k, v in params.items()]))
                    
                    # 執行查詢 (必須使用 await)
                    await cursor.execute(sql, params)
                    records = await cursor.fetchall()
                    
                    end_time = time.time()
                    execution_time = end_time - start_time
                    
                    # [保留除錯點 2]
                    if records:
                        sample = records[0]
                        logging.info(f"[RDBMS Repo Debug] 取得第一筆原始資料範例: {sample}")
                        if 'facility_tags' in sample:
                            logging.info(f"[RDBMS Repo Debug] 原始 facility_tags 內容: {sample['facility_tags']}")
                            logging.info(f"[RDBMS Repo Debug] 原始 facility_tags 型別: {type(sample['facility_tags'])}")
                    else:
                        logging.warning("[RDBMS Repo Debug] 查詢結果為空，請檢查 SQL 條件或資料庫編碼")
                    
                    logging.info(f"[RDBMS Repo] 查詢成功，取得 {len(records)} 筆資料，耗時: {execution_time:.5f}秒")
                    return list(records), execution_time

        # 捕捉 aiomysql 特有的錯誤
        except aiomysql.Error as e:
            logging.error(f"[RDBMS Repo] 資料庫錯誤: {e}")
            return [], 0.0
        except Exception as e:
            logging.error(f"[RDBMS Repo] 系統錯誤: {e}")
            return [], 0.0
        # 使用 async with 會自動處理連線釋放，不再需要手動 finally close