from qdrant_client import QdrantClient
from app.config import Config  # 引用你的配置文件

def init_qdrant():
    try:
        # 使用 config 裡面的參數進行連線
        client = QdrantClient(
            host=Config.VECTOR_DB_HOST, 
            port=Config.VECTOR_DB_PORT
        )
        
        # 測試連線並取得伺服器狀態
        info = client.get_collections()
        print(f"✅ 成功連線至 Qdrant: {Config.VECTOR_DB_HOST}:{Config.VECTOR_DB_PORT}")
        return client
    
    except Exception as e:
        print(f"❌ 連線失敗，請檢查 Docker 狀態或 config 設定: {e}")
        return None

if __name__ == "__main__":
    qdrant_client = init_qdrant()