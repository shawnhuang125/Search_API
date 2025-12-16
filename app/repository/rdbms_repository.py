from typing import List, Dict, Any
import logging
import pymysql # 引入 pymysql 來處理錯誤 Exception
from app.utils.db import get_db_connection # 引入工具函式


class RdbmsRepository:
    def __init__(self, use_mock: bool = True):
        # 初始化 RDBMS Repository
        logging.info("[RDBMS Repo] 初始化模式: REAL DB (將使用 utils.db 連線)")

    def execute_dynamic_query(self, sql: str, params: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        執行 SQL 查詢 (對外統一接口)
        """
        # 真實 DB 模式
        return self._execute_real_db(sql, params)


    #  實作細節：真實資料庫邏輯
    def _execute_real_db(self, sql: str, params: Dict[str, Any]) -> List[Dict[str, Any]]:
        connection = None
        try:
            # 從 utils.db 取得連線
            connection = get_db_connection()

            # 使用 context manager (with) 自動管理 Cursor 的開關
            # 因為在 utils.db 設定 DictCursor，這裡不需要額外設定
            with connection.cursor() as cursor:
                logging.info(f"[RDBMS Repo] 正在執行 SQL: {sql}")
                logging.debug(f"[RDBMS Repo] 參數: {params}")
                
                # 執行查詢
                cursor.execute(sql, params)
                
                # 獲取結果 (List of Dicts)
                records = cursor.fetchall()
                
                logging.info(f"[RDBMS Repo] 查詢成功，取得 {len(records)} 筆資料")
                return list(records)
                
        except pymysql.MySQLError as e:
            # 捕捉 pymysql 特有的錯誤
            logging.error(f"[RDBMS Repo] 資料庫錯誤: {e}")
            return []
        
        except Exception as e:
            # 捕捉其他未預期的錯誤
            logging.error(f"[RDBMS Repo] 系統錯誤: {e}")
            return []

        finally:
            # 務必手動關閉連線 (Connection)，因為 pymysql 的 connection 不會自動用 with 關閉
            if connection:
                connection.close()
                logging.debug("[RDBMS Repo] 資料庫連線已釋放")

    