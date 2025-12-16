from typing import List, Dict, Any, Optional
import logging
from app.models.search_dto import VectorSearchResult
from app.config import Config

try:
    from qdrant_client import QdrantClient
    from sentence_transformers import SentenceTransformer
    HAS_VECTOR_LIB = True
except ImportError:
    logging.warning("尚未安裝 qdrant-client 或 sentence-transformers，將強制使用 Mock 模式")
    HAS_VECTOR_LIB = False

class VectorRepository:
    def __init__(self, host: str = "localhost", port: int = 6333, use_mock: bool = False):
        self.use_mock = use_mock or (not HAS_VECTOR_LIB)
        self.collection_name = "restaurants"

        # ▼▼▼ 修改 1: 明確宣告型別為 Any，避免 Pylance 報錯說它是 None ▼▼▼
        self.client: Any = None
        self.model: Any = None

        target_host = host or Config.VECTOR_DB_HOST
        target_port = port or Config.VECTOR_DB_PORT

        if self.use_mock:
            logging.info("[Repo] 初始化模式: MOCK DATA (模擬資料)")
        else:
            logging.info(f"[Repo] 初始化模式: REAL QDRANT (連線至 {target_host}:{target_port})")
            try:
                self.client = QdrantClient(host=target_host, port=target_port)
                logging.info("正在載入 Embedding 模型 (all-MiniLM-L6-v2)...")
                self.model = SentenceTransformer('all-MiniLM-L6-v2')
                logging.info("模型載入完成")
            except Exception as e:
                logging.error(f"[Repo] 初始化失敗，將降級為 Mock 模式: {e}")
                self.use_mock = True

    def search_by_vector(self, keywords: str) -> List[VectorSearchResult]:
        logging.info(f"[Repo] 執行向量搜尋, 關鍵字: {keywords}")
        if not self.use_mock:
            return self._search_qdrant_logic(keywords)
        return self._search_mock_logic(keywords)

    def _search_qdrant_logic(self, keywords: str) -> List[VectorSearchResult]:
        results = []
        
        # ▼▼▼ 修改 2: 加入防呆檢查，告訴 Pylance 這裡絕對不會是 None ▼▼▼
        if self.client is None or self.model is None:
            logging.error("[Repo] Qdrant client 或 Model 未正確初始化")
            return []

        try:
            # Pylance 現在知道 self.model 不是 None 了，不會報錯
            query_vector = self.model.encode(keywords).tolist()

            # Pylance 現在知道 self.client 不是 None 了
            search_result = self.client.search(
                collection_name=self.collection_name,
                query_vector=query_vector,
                limit=5,
                with_payload=True
            )

            logging.info(f"[Qdrant] 搜尋完成，找到 {len(search_result)} 筆結果")

            for point in search_result:
                p = point.payload
                if not p: continue
                
                dto = VectorSearchResult(
                    id=p.get("id"),
                    name=p.get("name", "Unknown"),
                    cuisine_type=p.get("cuisine_type", []),
                    food_type=p.get("food_type", []),
                    flavor=p.get("flavor", []),
                    dish_name=p.get("dish_name", []),
                    review_text=p.get("review_text", ""),
                    metadata_quality=p.get("metadata_quality", "unknown")
                )
                results.append(dto)
            return results

        except Exception as e:
            logging.error(f"[Repo] Qdrant 搜尋發生錯誤: {e}")
            return []

    def _search_mock_logic(self, keywords: str) -> List[VectorSearchResult]:
        # ... (這部分維持原本的 Mock 邏輯不變) ...
        # 為節省篇幅省略，請保留你原本的 Mock 程式碼
        return []