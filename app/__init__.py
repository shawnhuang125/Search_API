import logging
import os
from logging.handlers import QueueHandler, QueueListener, TimedRotatingFileHandler
from queue import Queue
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routes.hybird_search_routes import place_search # 確保路徑與你的檔案結構一致

# 1. 初始化日誌目錄
log_dir = "logs"
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, "app.log")

# 2. 設定日誌格式
log_formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")

# 3. 建立 Handlers
# 檔案 Handler (日期輪轉)
file_handler = TimedRotatingFileHandler(
    log_file, 
    when="midnight", 
    interval=1, 
    backupCount=30, 
    encoding="utf-8"
)
file_handler.setFormatter(log_formatter)
file_handler.suffix = "%Y-%m-%d"

# 終端機 Handler
stream_handler = logging.StreamHandler()
stream_handler.setFormatter(log_formatter)

# 4. 建立非同步佇列與監聽器
log_queue = Queue(-1)
queue_handler = QueueHandler(log_queue)

# 監聽器負責從佇列取出日誌並交給指定的 handlers
# 加入 respect_handler_level=True 確保權限層級正確
listener = QueueListener(log_queue, file_handler, stream_handler, respect_handler_level=True)
listener.start()

# --- 核心修正區：接管全域 Logging ---

# 5. 取得 Root Logger 並清理
root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)

# 移除所有現有的 Handlers (包含 Uvicorn 預設產生的)
if root_logger.hasHandlers():
    root_logger.handlers.clear()

# 將 root logger 唯一的 handler 設定為我們的 queue_handler
root_logger.addHandler(queue_handler)

# 選擇性：讓 uvicorn 的系統訊息也進入我們的非同步隊列
logging.getLogger("uvicorn").handlers = [queue_handler]
logging.getLogger("uvicorn.access").handlers = [queue_handler]

# 建立專屬 Logger
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