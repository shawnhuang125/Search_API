# app/__init__.py
import logging
import os
from logging.handlers import QueueHandler, QueueListener, TimedRotatingFileHandler
from queue import Queue
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routes import place_search

# 1. 初始化日誌目錄
log_dir = "logs"
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, "app.log")

# 2. 設定日誌格式
log_formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")

# 3. 建立「日期輪轉」的 Handler
# when="midnight": 每天午夜切換檔案
# interval=1: 每 1 天切換一次
# backupCount=30: 保留最近 30 天的日誌，超過的會自動刪除
file_handler = TimedRotatingFileHandler(
    log_file, 
    when="midnight", 
    interval=1, 
    backupCount=30, 
    encoding="utf-8"
)
file_handler.setFormatter(log_formatter)
file_handler.suffix = "%Y-%m-%d" # 設定切換後的檔案後綴，如 app.log.2026-02-06

stream_handler = logging.StreamHandler()
stream_handler.setFormatter(log_formatter)

# 4. 建立非同步佇列與監聽器 (核心非同步邏輯)
log_queue = Queue(-1)
queue_handler = QueueHandler(log_queue)

# 監聽器會負責在背景執行緒中處理 file_handler 的寫入動作
listener = QueueListener(log_queue, file_handler, stream_handler)
listener.start()

# 5. 全域設定
logging.basicConfig(level=logging.INFO, handlers=[queue_handler])
logger = logging.getLogger("FastAPIApp")

# --- FastAPI 初始化 ---
app = FastAPI(title="Place Search Service", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(place_search)

@app.on_event("startup")
async def startup_event():
    logger.info("FastAPI service started (Async & Timed Rotation Enabled)")

@app.on_event("shutdown")
async def shutdown_event():
    # 關閉服務時，優雅關閉監聽器
    listener.stop()