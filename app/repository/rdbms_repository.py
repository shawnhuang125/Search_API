# 1. 引入 time 和 Tuple
import time
from typing import List, Dict, Any, Tuple 
import logging
import pymysql
from app.utils.db import get_db_connection

class RdbmsRepository:
    def __init__(self, use_mock: bool = True):
        logging.info("[RDBMS Repo] 初始化模式: REAL DB")

    # [修改點 1] 回傳型別提示改成 Tuple，代表會回傳 (資料列表, 秒數)
    def execute_dynamic_query(self, sql: str, params: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], float]:
        return self._execute_real_db(sql, params)

    def _execute_real_db(self, sql: str, params: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], float]:
        connection = None
        start_time = time.time()
        
        try:
            connection = get_db_connection()
            with connection.cursor() as cursor:
                # [新增除錯點 1]
                logging.info(f"[RDBMS Repo Debug] SQL 語句: {sql}")
                logging.info(f"[RDBMS Repo Debug] 綁定參數內容與型別: " + 
                             ", ".join([f"{k}: {v} ({type(v).__name__})" for k, v in params.items()]))
                
                cursor.execute(sql, params)
                records = cursor.fetchall()
                
                end_time = time.time()
                execution_time = end_time - start_time
                
                # [新增除錯點 2]
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

        # --- 必須補上這部分，否則會出現截圖中的 Pylance 錯誤 ---
        except pymysql.MySQLError as e:
            logging.error(f"[RDBMS Repo] 資料庫錯誤: {e}")
            return [], 0.0
        except Exception as e:
            logging.error(f"[RDBMS Repo] 系統錯誤: {e}")
            return [], 0.0
        finally:
            if connection:
                connection.close()