from typing import List, Dict, Any, Optional
from app.repository.vector_repository import VectorRepository
from app.models.search_dto import VectorSearchResult

class VectorService:
    def __init__(self):
        # 初始化倉管員
        self.repo = VectorRepository()

    def search(self, keywords: Any) -> Optional[List[Dict[str, Any]]]:
        """
        專門給 Hybrid Search Route 使用。
        處理可能回傳的 None 值，並轉換為 Dict 格式。
        """
        # 把 list 轉成字串 (因為 repo 接收 str)
        query_str = " ".join(keywords) if isinstance(keywords, list) else keywords
        
        # 1. 呼叫倉管 (注意：results 現在可能是 List 或 None)
        results: Optional[List[VectorSearchResult]] = self.repo.search_by_vector(query_str)
        
        # 2. 處理 None 的情況
        # 如果 results 是 None，代表 Repo 決定跳過向量搜尋 (Payload 未就緒)
        # 我們直接把 None 傳回給 API Route，API 會再傳給 SQL Builder
        if results is None:
            return None
        
        # 3. 如果有結果 (或者是空列表 [])，才進行轉換
        # 使用 vars(r) 或 r.__dict__ 都可以
        return [vars(r) for r in results]