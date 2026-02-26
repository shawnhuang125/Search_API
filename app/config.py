# app/config.py
import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev_key") # 如果沒有flask需要使用的SECRET_KEY參數則預設為dev_key

    DB_HOST = os.getenv("DB_HOST", "127.0.0.1") # 如果沒有資料庫host,預設為127.0.0.1也就是本機端連線
    DB_PORT = int(os.getenv("DB_PORT", 3306)) # 如果沒有資料庫Port,預設為3306
    DB_USER = os.getenv("DB_USER", "root") # 如果沒有資料庫user,預設為root
    DB_PASSWORD = os.getenv("DB_PASSWORD", "") # 如果沒有資料庫密碼,預設為空
    DB_NAME = os.getenv("DB_NAME", "") # 如果沒有資料庫名稱,預設為空
    # 資料庫連線url
    DATABASE_URL = (
        f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    )

    IMAGES_URL = os.getenv("IMAGES_URL", "http://localhost/images/")

    VECTOR_DB_HOST = os.environ.get('Vector_DB_HOST', 'localhost')
    VECTOR_DB_PORT = int(os.environ.get('Vector_DB_PORT', 6333))