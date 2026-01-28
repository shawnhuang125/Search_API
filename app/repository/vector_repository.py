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
        self.payload_ready = False 
        self.client: Any = None
        self.model: Any = None

        target_host = host or Config.VECTOR_DB_HOST
        target_port = port or Config.VECTOR_DB_PORT

        # 如果是實體連線模式才輸出日誌，Mock 模式則保持沉默
        if not self.use_mock:
            logging.info(f"[Repo] 初始化模式: REAL QDRANT (連線至 {target_host}:{target_port})")
            try:
                self.client = QdrantClient(host=target_host, port=target_port)
                # 更改模型路徑
                model_name = './m3_food_finetuned'
                logging.info(f"正在載入 BGE-M3 嵌入模型...")
                
                self.model = SentenceTransformer(model_name)
                
                # BGE-M3 建議在檢索時，Query 端可以加上特定的 prefix (選配，視微調情況而定)
                # 但在 SentenceTransformers 中直接使用即可
                logging.info("BGE-M3 模型載入完成")
            except Exception as e:
                logging.info("模型載入失敗，切換至 Mock 模式")
                self.use_mock = True

    def search_by_vector(self, keywords: str) -> List[VectorSearchResult] | None:
        
        logging.info(f"[Repo] 執行向量搜尋, 關鍵字: {keywords}")

        if not self.payload_ready:
            logging.warning("[Repo] Payload 尚未就緒，回傳 None 以跳過 SQL ID 過濾")
            return None
        
        if not self.use_mock:
            return self._search_qdrant_logic(keywords)
        
        return self._search_mock_logic(keywords)

    def _search_qdrant_logic(self, keywords: str) -> List[VectorSearchResult]:
        results = []
        
        if self.client is None or self.model is None:
            logging.error("[Repo] Qdrant client 或 Model 未正確初始化")
            return []

        try:
            # 修改 1: 加入 normalize_embeddings，這對 BGE 系列效果更好
            # 如果顯存吃緊，可以考慮加入 batch_size=1
            query_vector = self.model.encode(
                keywords, 
                normalize_embeddings=True 
            ).tolist()

            # 修改 2: 這裡建議把 limit 變成變數，方便未來調整
            search_result = self.client.search(
                collection_name=self.collection_name,
                query_vector=query_vector,
                limit=10,  # 稍微放寬一點，讓後面的 RAG 有更多素材
                with_payload=True
            )

            logging.info(f"[Qdrant] 搜尋完成，找到 {len(search_result)} 筆結果")

            for point in search_result:
                p = point.payload
                if not p: continue
                
                # 這裡保留你原本的 DTO 轉換邏輯
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
        logging.info("[Repo] 觸發攔截邏輯：回傳功能未支援說明")
        
        # 回傳一筆特殊的 Mock 資料告知狀態
        return []
