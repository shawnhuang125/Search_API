# app/repository/vector_repository.py
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
        self.collection_name = Config.COLLECTION_NAME
        self.payload_ready = True
        self.client: Any = None
        self.model: Any = None
        
        # 優先讀取 Config 裡的 192.168.1.112
        target_host = host or Config.VECTOR_DB_HOST
        target_port = port or Config.VECTOR_DB_PORT

        if not self.use_mock:
            # 這裡 Log 會顯示真正的連線目標，請檢查啟動時是不是顯示 192.168.1.112
            logging.info(f"[Repo] 初始化模式: REAL QDRANT (連線至 {target_host}:{target_port})")
            try:
                # 走 HTTP 協議
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

    # 向量搜尋功能(只針對rdbms過濾出來的店家ID列表去做向量運算)
    async def search_in_ids(self, query_str: str, rdbms_ids: List[Any],must_have_tags: List[str] = None,base_amenities: List[str] = None ) -> List[VectorSearchResult]:
        # 前置處理
        try:
            # 因為 Qdrant 存的店家id是字串，必須把 SQL 拿到的店家id資料型態轉成字串
            clean_ids = [int(i) for i in rdbms_ids if i is not None]
        except (ValueError, TypeError):
            return []
        if not clean_ids: return []

        filter_conditions = [
            qmodels.FieldCondition(key="place_id", match=qmodels.MatchAny(any=clean_ids))
        ]

        # 2. 如果有指定的服務標籤，加入 must 條件
        if must_have_tags:
            for tag in must_have_tags:
                filter_conditions.append(
                    # 去掉 "payload."，直接寫欄位名 (除非你的 JSON 裡面真的包了一層 payload)
                    qmodels.FieldCondition(key="facility_tags", match=qmodels.MatchValue(value=tag))
                )

        search_filter = qmodels.Filter(must=filter_conditions)

        # 將自然語言搜尋字串轉成向量
        async with self.gpu_limit:
            query_vector = self.model.encode(query_str, normalize_embeddings=True).tolist()
        

        try:
            logging.info(f"執行語意排序，範圍筆數: {len(clean_ids)}")
            response = await self.client.query_points(
                collection_name=self.collection_name,
                query=query_vector,
                query_filter=search_filter,  # 這裡只剩下 ID 範圍過濾
                limit=30,
                with_payload=True
            )
            results = response.points
        except AttributeError:
            # ... 舊版 API 相容邏輯維持原樣 ...
            results = await self.client.search(
                collection_name=self.collection_name,
                query_vector=query_vector,
                query_filter=search_filter,
                limit=30,
                with_payload=True
            )

        # 4. 回傳結果
        return [VectorSearchResult(
                id=res.payload.get("place_id"), 
                score=res.score,
                review_summary=res.payload.get("review_summary", "")
                ) 
                for res in results if res.payload
                ]