from typing import List, Dict, Any
import logging
import pymysql # 引入 pymysql 來處理錯誤 Exception
from app.utils.db import get_db_connection # 引入工具函式
import re

class RdbmsRepository:
    def __init__(self, use_mock: bool = True):
        """
        初始化 RDBMS Repository
        :param use_mock: True = 回傳假資料, False = 連線真實 DB
        """
        self.use_mock = use_mock
        
        if self.use_mock:
             logging.info("[RDBMS Repo] 初始化模式: MOCK DATA")
        else:
             logging.info("[RDBMS Repo] 初始化模式: REAL DB (將使用 utils.db 連線)")

    def execute_dynamic_query(self, sql: str, params: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        執行 SQL 查詢 (對外統一接口)
        """
        # Mock 模式
        if self.use_mock:
            return self._execute_mock_db(sql, params)

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
                return records
                
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


    #  Mock 資料
    def _execute_mock_db(self, sql: str, params: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        回傳符合 HybridSQLBuilder SELECT 欄位的假資料
        """
        logging.info("[RDBMS Repo] 回傳模擬資料...")

        mock_data = [
                {
                "id": 1,
                "name": "黑盤PASTA永康崑大店",
                "address": "710台灣台南市永康區崑大路226號",
                "phone": "06 205 8622",
                "website": "nan",
                "opening_hours": {
                    "星期一": "11:30 - 15:00, 17:00 - 21:00",
                    "星期二": "11:30 - 15:00, 17:00 - 21:00",
                    "星期三": "11:30 - 15:00, 17:00 - 21:00",
                    "星期四": "11:30 - 15:00, 17:00 - 21:00",
                    "星期五": "11:30 - 15:00, 17:00 - 21:00",
                    "星期六": "11:30 - 15:00, 17:00 - 21:00",
                    "星期日": "11:30 - 15:00, 17:00 - 21:00"
                },
                "rating": 4.6,
                "lat": "22.9985877",
                "lng":"120.2534950",
                "source": "Google-PlaceAPI"
                },
                {
                    "id": 2,
                    "name": "龍門燄",
                    "address": "710台灣台南市永康區崑大路155巷31號",
                    "phone": "0968 683 618",
                    "website": "https://www.facebook.com/1267420986753662/",
                    "opening_hours": {
                        "星期一": "18:00 - 21:00",
                        "星期二": "18:00 - 21:00",
                        "星期三": "18:00 - 21:00",
                        "星期四": "18:00 - 21:00",
                        "星期五": "18:00 - 21:00",
                        "星期六": "18:00 - 21:00",
                        "星期日": "18:00 - 21:00"
                    },
                    "business_status":"正常營運",
                    "rating": 4.7,
                    "lat": "22.9985877",
                    "lng":"120.2534950",
                    "source": "Google-PlaceAPI"
                },
                {
                    "id": 3,
                    "name": "桶好呷現滷滷味",
                    "address": "710台灣台南市永康區大灣路1028號",
                    "phone": "0977 373 899",
                    "website": "https://m.facebook.com/pages/%E6%A1%B6%E5%A5%BD%E5%91%B7%E7%8F%BE%E6%BB%B7%E6%BB%B7%E5%91%B3%E6%B0%B8%E5%BA%B7%E5%B4%91%E5%A4%A7%E5%BA%97/281739208670082",
                    "opening_hours": {
                        "星期一": "17:00 - 23:00",
                        "星期二": "17:00 - 23:00",
                        "星期三": "17:00 - 23:00",
                        "星期四": "17:00 - 23:00",
                        "星期五": "17:00 - 23:00",
                        "星期六": "17:00 - 23:00",
                        "星期日": "17:00 - 23:00"
                    },
                    "business_status":"正常營運",
                    "rating": 4.3,
                    "lat": "22.9978174",
                    "lng":"120.2570107",
                    "source": "Google-PlaceAPI"
                },
                {
                    "id": 4,
                    "name": "付家多采貴州風味羊肉粉",
                    "address": "710台灣台南市永康區崑大路35號",
                    "phone": "0931 925 927",
                    "website": "https://m.facebook.com/pages/%E6%A1%B6%E5%A5%BD%E5%91%B7%E7%8F%BE%E6%BB%B7%E6%BB%B7%E5%91%B3%E6%B0%B8%E5%BA%B7%E5%B4%91%E5%A4%A7%E5%BA%97/281739208670082",
                    "opening_hours": {
                        "星期一": "17:00 - 23:00",
                        "星期二": "17:00 - 23:00",
                        "星期三": "17:00 - 23:00",
                        "星期四": "17:00 - 23:00",
                        "星期五": "17:00 - 23:00",
                        "星期六": "17:00 - 23:00",
                        "星期日": "17:00 - 23:00"
                    },
                    "business_status":"正常營運",
                    "rating": 4.7,
                    "lat": "22.9978174",
                    "lng":"120.2570107",
                    "source": "Google-PlaceAPI"
                },
                {
                    "id": 5,
                    "name": "緯郎壽司",
                    "address": "710台灣台南市永康區崑大路81號",
                    "phone": "0979 322 991",
                    "website": "nan",
                    "opening_hours": {
                        "星期一": "休息",
                        "星期二": "11:00 - 14:00, 16:30 - 21:30",
                        "星期三": "11:00 - 14:00, 16:30 - 21:30",
                        "星期四": "11:00 - 14:00, 16:30 - 21:30",
                        "星期五": "11:00 - 14:00, 16:30 - 21:30",
                        "星期六": "11:00 - 14:00, 16:30 - 21:30",
                        "星期日": "11:00 - 14:00, 16:30 - 21:30"
                    },
                    "business_status":"正常營運",
                    "rating": 4.9,
                    "lat": "22.9979171",
                    "lng":"120.2563607",
                    "source": "Google-PlaceAPI"
                },
                {
                    "id": 6,
                    "name": "饗御鐵板燒",
                    "address": "710台灣台南市永康區崑大路258號",
                    "phone": "06 205 0605",
                    "website": "https://www.facebook.com/profile.php?id=100093020922550&mibextid=LQQJ4d",
                    "opening_hours": {
                        "星期一": "11:00 - 22:00",
                        "星期二": "11:00 - 22:00",
                        "星期三": "11:00 - 22:00",
                        "星期四": "11:00 - 22:00",
                        "星期五": "11:00 - 22:00",
                        "星期六": "11:00 - 22:00",
                        "星期日": "11:00 - 22:00"
                    },
                    "business_status":"正常營運",
                    "rating": 4.9,
                    "lat": "22.9987839",
                    "lng":"120.2529180",
                    "source": "Google-PlaceAPI"
                },
                {
                    "id": 7,
                    "name": "四川麻辣串串香",
                    "address": "710台灣台南市永康區大灣路962-1號",
                    "phone": "0900 228 415",
                    "website": "nan",
                    "opening_hours": {
                        "星期一": "17:00 - 02:00",
                        "星期二": "17:00 - 02:00",
                        "星期三": "17:00 - 02:00",
                        "星期四": "17:00 - 02:00",
                        "星期五": "17:00 - 02:00",
                        "星期六": "17:00 - 02:00",
                        "星期日": "17:00 - 02:00"
                    },
                    "business_status":"正常營運",
                    "rating": 4.6,
                    "lat": "22.9994439",
                    "lng":"120.2544590",
                    "source": "Google-PlaceAPI"
                },
                {
                    "id": 8,
                    "name": "阿明食堂",
                    "address": "710台灣台南市永康區大灣路927號",
                    "phone": "0938 308 815",
                    "website": "nan",
                    "opening_hours": {
                        "星期一": "06:00 - 13:00",
                        "星期二": "06:00 - 13:00",
                        "星期三": "06:00 - 13:00",
                        "星期四": "06:00 - 13:00",
                        "星期五": "06:00 - 13:00",
                        "星期六": "06:00 - 13:00",
                        "星期日": "休息"
                    },
                    "business_status":"正常營運",
                    "rating": 4.2,
                    "lat": "22.9990267",
                    "lng":"120.2539404",
                    "source": "Google-PlaceAPI"
                },
                {
                    "id": 9,
                    "name": "Thai泰拌飯東南亞餐盒",
                    "address": "710台灣台南市永康區大灣路723號",
                    "phone": "06 272 2935",
                    "website": "https://www.facebook.com/banbanfan2021",
                    "opening_hours": {
                        "星期一": "休息",
                        "星期二": "11:00 - 14:30, 16:00 - 20:00",
                        "星期三": "11:00 - 14:30, 16:00 - 20:00",
                        "星期四": "11:00 - 14:30, 16:00 - 20:00",
                        "星期五": "11:00 - 14:30, 16:00 - 20:00",
                        "星期六": "11:00 - 14:30, 16:00 - 20:00",
                        "星期日": "11:00 - 14:30, 16:00 - 20:00"
                    },
                    "business_status":"正常營運",
                    "rating": 4.9,
                    "lat": "22.9997656",
                    "lng":"120.2576649",
                    "source": "Google-PlaceAPI"
                },
                {
                    "id": 10,
                    "name": "大鮨灣日本料理",
                    "address": "710台灣台南市永康區大灣路660號",
                    "phone": "06 272 0029",
                    "website": "https://www.facebook.com/%E5%A4%A7%E9%AE%A8%E7%81%A3-101116648658411",
                    "opening_hours": {
                        "星期一": "休息",
                        "星期二": "11:00 - 13:30, 17:00 - 19:30",
                        "星期三": "11:00 - 13:30, 17:00 - 19:30",
                        "星期四": "11:00 - 13:30, 17:00 - 19:30",
                        "星期五": "11:00 - 13:30, 17:00 - 19:30",
                        "星期六": "11:00 - 13:30, 17:00 - 19:30",
                        "星期日": "11:00 - 13:30, 17:00 - 19:30"
                    },
                    "business_status":"正常營運",
                    "rating": 4.8,
                    "lat": "23.0010813",
                    "lng":"120.2629993",
                    "source": "Google-PlaceAPI"
                }
        ]
        
        final_results = []
        target_ids = set()

        if "p.id =" in sql:
            for val in params.values():
                if isinstance(val, int):
                    target_ids.add(val)

        # 情況 B: 向量搜尋後的查詢 (SQL 裡有 "p.id IN")
        # 這時候 ID 是直接寫死在 SQL 字串裡 (例如 IN (9, 10))
        if "p.id IN" in sql:
            # 使用 Regex 抓出括號內的數字
            matches = re.findall(r"p\.id IN \(([\d, ]+)\)", sql)
            if matches:
                # matches[0] 會是 "9, 10" 這樣的字串
                id_list_str = matches[0]
                for x in id_list_str.split(','):
                    if x.strip().isdigit():
                        target_ids.add(int(x.strip()))
        
        logging.info(f"[Mock DB] 解析出的目標 ID: {target_ids}")
            
        for row in mock_data:
            if target_ids:
                # 如果有指定 ID (不管是單個還是列表)，必須精確符合才回傳
                if row['id'] in target_ids:
                    final_results.append(row)
            else:
                # 如果沒有指定 ID，回傳全部
                final_results.append(row)


        logging.info(f"[RDBMS Repo] Mock 回傳 {len(final_results)} 筆")
        return final_results