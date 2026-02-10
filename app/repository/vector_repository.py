from typing import List, Dict, Any, Optional
from app.models.search_dto import VectorSearchResult
from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models as qmodels
from app.config import Config
import logging
import asyncio

try:
    from qdrant_client import QdrantClient
    from sentence_transformers import SentenceTransformer
    HAS_VECTOR_LIB = True
except ImportError:
    logging.warning("尚未安裝 qdrant-client 或 sentence-transformers，將強制使用 Mock 模式")
    HAS_VECTOR_LIB = False

class VectorRepository:
    def __init__(self, host: str = None, port: int = None, use_mock: bool = False):
        self.gpu_limit = asyncio.Semaphore(10)
        self.use_mock = use_mock or (not HAS_VECTOR_LIB)
        self.collection_name = "restaurants"
        self.payload_ready = True
        self.client: Any = None
        self.model: Any = None
        
        # 1. 確保優先讀取 Config 裡的 192.168.1.112
        target_host = host or Config.VECTOR_DB_HOST
        target_port = port or Config.VECTOR_DB_PORT

        if not self.use_mock:
            # 2. 這裡 Log 會顯示真正的連線目標，請檢查啟動時是不是顯示 192.168.1.112
            logging.info(f"[Repo] 初始化模式: REAL QDRANT (連線至 {target_host}:{target_port})")
            try:
                # 3. 💡 關鍵修正：prefer_grpc=False
                # 因為你說 6333 是正常的（儀表板可開），所以必須走 HTTP 協議
                self.client = AsyncQdrantClient(
                    host=target_host, 
                    port=int(target_port), 
                    prefer_grpc=False 
                )
                
                model_path = './m3_food_finetuned'
                logging.info(f"正在載入 BGE-M3 嵌入模型...")
                self.model = SentenceTransformer(model_path)
                
                import torch
                device = "cuda" if torch.cuda.is_available() else "cpu"
                logging.info(f"模型載入完成，設備: {device}")
            except Exception as e:
                logging.error(f"模型或連線載入失敗: {e}")
                self.use_mock = True


    async def search_by_vector(self, keywords: str) -> List[VectorSearchResult] | None:
        
        logging.info(f"[Repo] 執行向量搜尋, 關鍵字: {keywords}")

        if not self.payload_ready:
            logging.warning("[Repo] Payload 尚未就緒，回傳 None 以跳過 SQL ID 過濾")
            return None
        
        if not self.use_mock:
            return await self._search_qdrant_logic(keywords)
        
        return self._search_mock_logic(keywords)

    async def _search_qdrant_logic(self, keywords: str) -> List[VectorSearchResult]:
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
            search_result = await self.client.search(
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
                    id=p.get("original_id"),
                    name=p.get("name", "Unknown"),
                    cuisine_type=p.get("cuisine_type", []),
                    food_type=p.get("food_type", []),
                    flavor=p.get("flavor", []),
                    # dish_name=p.get("dish_name", []),
                    # review_text=p.get("review_text", ""),
                    level=p.get("level", "unknown")
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
    
    # 向量搜尋功能(只針對rdbms過濾出來的店家ID列表去做向量運算)
    async def search_in_ids(self, query_str: str, rdbms_ids: List[Any]) -> List[VectorSearchResult]:
        # 1. 前置處理 (這部分你做得很對)
        try:
            # 因為 Qdrant 存的是字串，我們必須把 SQL 拿到的數字轉成字串
            clean_ids = [str(i) for i in rdbms_ids if i is not None]
        except (ValueError, TypeError):
            return []
        if not clean_ids: return []

        # 2. 向量轉換
        async with self.gpu_limit:
            query_vector = self.model.encode(f"想吃{query_str}", normalize_embeddings=True).tolist()
        
        search_filter = qmodels.Filter(
            must=[qmodels.FieldCondition(key="original_id", match=qmodels.MatchAny(any=clean_ids))]
        )

        # 3. 執行搜尋 (自動適應 API 版本)
        try:
            logging.info("嘗試使用 query_points 進行搜尋...")
            # 優先嘗試最新版本的 API
            response = await self.client.query_points(
                collection_name=self.collection_name,
                query=query_vector,
                query_filter=search_filter,
                limit=10,
                with_payload=True
            )
            results = response.points
        except AttributeError:
            logging.info("query_points 不存在，嘗試使用 search...")
            try:
                # 嘗試傳統的 search API
                results = await self.client.search(
                    collection_name=self.collection_name,
                    query_vector=query_vector,
                    query_filter=search_filter,
                    limit=10,
                    with_payload=True
                )
            except AttributeError as e:
                # 如果都失敗，印出所有方法清單
                import inspect
                valid_methods = [m for m, _ in inspect.getmembers(self.client) if not m.startswith('_')]
                logging.error(f"致命錯誤：找不到搜尋方法。可用方法有：{valid_methods}")
                raise e

        # 4. 回傳結果
        return [VectorSearchResult(id=res.payload.get("original_id"), score=res.score) for res in results if res.payload]