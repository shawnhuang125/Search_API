# utils/db.py
# 用於讀取環境變數並進行資料庫連線
import pymysql # 使用pymysql進行資料庫連線
from app.config import Config
# 資料庫連線
def get_db_connection():
    """
    建立並回傳一個新的資料庫連線。
    使用者要自己關閉 conn.close()。
    """
    return pymysql.connect(
        host=Config.DB_HOST,
        port=Config.DB_PORT,
        user=Config.DB_USER,
        password=Config.DB_PASSWORD,
        database=Config.DB_NAME,
        cursorclass=pymysql.cursors.DictCursor, # 讓查詢結果變成字典型態 (key: value)
        
        # 進階資料庫連線設定
        autocommit=True,  # 可以手動控制 commit
        charset="utf8mb4"  # 避免以後有人存 Emoji 你的資料庫會報錯
    )
