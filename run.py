# main.py

import logging
import os
from app import create_app
from app.database_init import init_database
from app.config import Config

# ================================
# Initialize Logging (English only)
# ================================
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

logging.info("Logger initialized (run.py).")

# ================================
# Initialize Database
# ================================
#if init_database():
#    logging.info(f"Database initialization completed. Host: {Config.DB_HOST}, Port:{Config.DB_PORT}")
#else:
#    logging.warning("Database initialization failed.")

# ================================
# Start Flask App
# ================================
app = create_app()

if __name__ == "__main__":
    logging.info("Starting Flask server...")
    app.run(host="0.0.0.0", port=5004, debug=True)
