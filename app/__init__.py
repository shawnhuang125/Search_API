import logging
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routes import place_search  # 修改後的 Router

# 1. 初始化日誌設定
log_dir = "logs"
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, "app.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(log_file, encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("FastAPIApp")

# 2. 初始化 FastAPI
app = FastAPI(title="Place Search Service", version="2.0.0")

# 3. 啟用 CORS (取代 Flask-CORS)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 根據需求調整
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 4. 註冊 Router (取代 Blueprint)
app.include_router(place_search, prefix="/place_search")

@app.on_event("startup")
async def startup_event():
    logger.info("FastAPI service started successfully")