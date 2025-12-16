# run.py

import logging
import os
from app import create_app
from app.config import Config


# Initialize Logging
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


logging.info(f"Database: MySQL. Connection successfully! Host: {Config.DB_HOST}, Port:{Config.DB_PORT}, Database: {Config.DB_NAME}, User:{Config.DB_USER}")
logging.info(f"Database: Qdrant. Connection successfully! Host: {Config.VECTOR_DB_HOST}, Port:{Config.VECTOR_DB_PORT}")
logging.info(f"Connect to Photo Service Successfully. URL:{Config.IMAGES_URL}")
# print(f"Database: MySQL. Connection successfully! Host: {Config.DB_HOST}, Port:{Config.DB_PORT}, Database: {Config.DB_NAME}, User:{Config.DB_USER}")
# Start Flask App
app = create_app()

if __name__ == "__main__":
    logging.info("Starting Flask server...")
    app.run(host="0.0.0.0", port=5004, debug=True)
