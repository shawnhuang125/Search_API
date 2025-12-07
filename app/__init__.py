# app/__init__.py
# 這裡是app的服務總入口
# 所有的陸游與子路由都會在這裡註冊
import logging
import os
from flask import Flask
from flask_cors import CORS
from app.config import Config

# 直接載入子藍圖
# 可擴充如 pages_bp, db_bp需要在這裡匯入from app.routes import [路由物件名稱]  
from app.routes import place_search_bp

# 初始化flask服務
def create_app():
    app = Flask(__name__)

    # ----------------------
    # 載入設定
    # ----------------------
    app.config.from_object(Config)
    # 啟用 CORS,沒有這個無法實現前後端通訊
    CORS(app)
    # Logger 設定,這是app的logger設定可以方便在/logs/app.log進行除錯
    log_dir = "logs"
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, "app.log")

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"), # 編碼
            logging.StreamHandler()
        ]
    )

    logger = logging.getLogger("FlaskApp") # 建立logger物件
    logger.info("Logger initialized")

    # 註冊 Blueprint
    app.register_blueprint(place_search_bp, url_prefix="/place_search")
    # app.register_blueprint(pages_bp, url_prefix="/api/pages")
    # app.register_blueprint(db_bp, url_prefix="/api/databases")

    return app
