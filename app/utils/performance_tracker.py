# ./app/utils/performance_tracker.py
import csv
import os
import logging
from app.config import Config

def log_performance_to_csv(metrics: dict):
    file_exists = os.path.isfile(Config.PERFORMANCE_LOG_PATH)
    
    header = [
        "搜尋架構", "目前店家總數", "SQL_Service耗時", 
        "SQL轉Vector過渡耗時", "Qdrant查詢耗時", "指標排序耗時", "總耗時(Route層)"
    ]
    
    try:
        with open(Config.PERFORMANCE_LOG_PATH, mode='a', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=header)
            if not file_exists:
                writer.writeheader()
            
            writer.writerow({
                "搜尋架構": Config.SEARCH_ARCHITECTURE,
                "目前店家總數": Config.CURRENT_PLACE_COUNT,
                "SQL_Service耗時": metrics.get("sql_service"),
                "SQL轉Vector過渡耗時": metrics.get("transition"),
                "Qdrant查詢耗時": metrics.get("qdrant"),
                "指標排序耗時": metrics.get("ranking"),
                "總耗時(Route層)": metrics.get("total")
            })
    except Exception as e:
        logging.error(f"寫入效能 CSV 失敗: {e}")