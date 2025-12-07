from typing import List, Dict, Any
import logging
import pymysql # 引入 pymysql 來處理錯誤 Exception
from app.utils.db import get_db_connection # 引入工具函式

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
                    "id": 203,
                    "name": "小豪洲沙茶爐",
                    "address": "台南市中西區中正路138巷",
                    "rating": 4.5,
                    "service_tags": "冷氣開放,適合聚餐,老店",
                    "merchant_categories": "火鍋,沙茶爐"
                },
                {
                    "id": 204,
                    "name": "松大沙茶爐",
                    "address": "台南市中西區成功路439號",
                    "rating": 4.3,
                    "service_tags": "宵夜,在地人推薦",
                    "merchant_categories": "火鍋,晚餐"
                },
                {
                    "id": 205,
                    "name": "詹記麻辣火鍋 (台北店)",
                    "address": "台北市大安區和平東路",
                    "rating": 4.8,
                    "service_tags": "訂位制,網美店,質感",
                    "merchant_categories": "麻辣鍋,高級餐廳"
                },
                {
                    "id": 206,
                    "name": "文章牛肉湯 (安平總店)",
                    "address": "台南市安平區安平路590號",
                    "rating": 4.6,
                    "service_tags": "排隊名店,24小時,無停車場",
                    "merchant_categories": "牛肉湯,台式早餐"
                },
                {
                    "id": 207,
                    "name": "阿裕牛肉涮涮鍋 (崑崙店)",
                    "address": "台南市仁德區崑崙路733-1號",
                    "rating": 4.7,
                    "service_tags": "附設停車場,適合聚餐,冷氣開放",
                    "merchant_categories": "火鍋,溫體牛"
                },
                {
                    "id": 208,
                    "name": "丹丹漢堡 (永康店)",
                    "address": "台南市永康區中正南路430號",
                    "rating": 4.5,
                    "service_tags": "南部限定,高CP值,現金交易",
                    "merchant_categories": "速食,早餐"
                },
                {
                    "id": 209,
                    "name": "矮仔成蝦仁飯",
                    "address": "台南市中西區海安路一段66號",
                    "rating": 4.1,
                    "service_tags": "老店,路邊攤風格,出餐快",
                    "merchant_categories": "小吃,飯食"
                },
                {
                    "id": 210,
                    "name": "蜷尾家甘味處散步甜食",
                    "address": "台南市中西區正興街92號",
                    "rating": 4.3,
                    "service_tags": "排隊名店,無內用座位,網美打卡",
                    "merchant_categories": "甜點,冰淇淋"
                },
                {
                    "id": 211,
                    "name": "悅津鹹粥",
                    "address": "台南市中西區西門路二段332號",
                    "rating": 4.2,
                    "service_tags": "24小時,冷氣開放,老店",
                    "merchant_categories": "海鮮粥,台式早餐"
                },
                {
                    "id": 212,
                    "name": "鬍鬚忠牛肉湯",
                    "address": "台南市中西區民族路三段91號",
                    "rating": 4.6,
                    "service_tags": "宵夜,在地人推薦,現金交易",
                    "merchant_categories": "牛肉湯,熱炒"
                },
                {
                    "id": 213,
                    "name": "鼎泰豐 (台南南紡店)",
                    "address": "台南市東區中華東路一段366號",
                    "rating": 4.8,
                    "service_tags": "服務好,百貨公司,適合家庭聚餐",
                    "merchant_categories": "中式料理,港式點心"
                },
                {
                    "id": 214,
                    "name": "大東夜市",
                    "address": "台南市東區林森路一段276號",
                    "rating": 4.4,
                    "service_tags": "露天,人多擁擠,無冷氣",
                    "merchant_categories": "夜市,小吃集合"
                },
                {
                    "id": 215,
                    "name": "永樂燒肉飯",
                    "address": "台南市中西區民族路三段16號",
                    "rating": 4.0,
                    "service_tags": "平價,附沙拉,老店",
                    "merchant_categories": "便當,燒肉"
                }
        ]
        
        final_results = []
        for row in mock_data:
            if str(row['id']) in sql: 
                final_results.append(row)
            elif "p.id IN" not in sql:
                final_results.append(row)

        logging.info(f"[RDBMS Repo] Mock 回傳 {len(final_results)} 筆")
        return final_results