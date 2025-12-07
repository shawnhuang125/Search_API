from typing import List
from app.repository.vector_repository import VectorRepository
from app.models.search_dto import VectorSearchResult

class VectorService:
    def __init__(self):
        # 初始化倉管員
        self.repo = VectorRepository()

    def search(self, keywords: list) -> List[dict]:
        """
        專門給 Hybrid Search Route 使用。
        回傳原始的 Dictionary (包含 id)，而不是格式化後的 UI 資料。
        """
        # 把 list 轉成字串 (因為 repo 接收 str)
        query_str = " ".join(keywords) if isinstance(keywords, list) else keywords
        
        # 1. 呼叫倉管
        results: List[VectorSearchResult] = self.repo.search_by_vector(query_str)
        
        # 2. 轉成 Dict 回傳 (保留 id 欄位！)
        # 使用 __dict__ 可以快速把 Object 轉成 Dictionary
        return [r.__dict__ for r in results]
    