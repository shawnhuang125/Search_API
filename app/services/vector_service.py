from typing import List, Dict, Any, Optional
from app.repository.vector_repository import VectorRepository
from app.models.search_dto import VectorSearchResult
import math

class VectorService:
    def __init__(self):
        # 初始化倉管員
        self.repo = VectorRepository()

    async def search_and_rank(
        self, 
        keywords: Any, 
        db_results: List[Dict[str, Any]], 
        top_k: int = 3
    ) -> Optional[List[Dict[str, Any]]]:
        """
        執行向量搜尋並根據 (相似度*0.6) + (星等*0.3) + (評論數*0.1) 進行重排序
        """
        # 1. 前置處理：將 keywords 轉為字串
        query_str = " ".join(keywords) if isinstance(keywords, list) else keywords
        
        # 2. 取得 RDBMS 篩選後的 ID 列表，用於限制向量搜尋範圍 (Pre-filtering)
        rdbms_ids = [row.get("id") for row in db_results]
        if not rdbms_ids:
            return []

        # 3. 呼叫 Repo 進行向量搜尋
        # 假設你的 repo 有支援 search_in_ids，若無則改用 search_by_vector 後在記憶體篩選
        vector_results: Optional[List[VectorSearchResult]] = self.repo.search_in_ids(query_str, rdbms_ids)
        
        if vector_results is None:
            return None

        # 混合權重計算 (Hybrid Ranking)
        return self._apply_hybrid_ranking(vector_results, db_results, top_k)
    
    async def _apply_hybrid_ranking(
        self, 
        vector_results: List[VectorSearchResult], 
        db_results: List[Dict[str, Any]], 
        top_k: int
    ) -> List[Dict[str, Any]]:
        
        # 將 db_results 轉為 map 方便快速比對
        db_map = {str(row['id']): row for row in db_results}
        
        # 找出最大評論數用於歸一化 (避免除以零)
        all_counts = [row.get('user_ratings_total', 0) for row in db_results]
        max_reviews = max(all_counts) if all_counts else 1
        
        ranked_list = []

        for v in vector_results:
            v_id = str(v.id)
            if v_id in db_map:
                store = db_map[v_id].copy() # 複製一份避免污染原始資料
                
                # A. 語意相似度 (0.0 - 1.0)
                sim_score = v.score
                
                # B. 星等分數 (將 0-5 分縮放至 0-1)
                rating_score = float(store.get('rating', 0)) / 5.0
                
                # C. 人氣分數 (使用對數縮放，平滑化極端值)
                reviews_count = store.get('user_ratings_total', 0)
                pop_score = math.log1p(reviews_count) / math.log1p(max_reviews) if max_reviews > 0 else 0

                # 總分計算: (0.6, 0.3, 0.1)
                final_score = (sim_score * 0.6) + (rating_score * 0.3) + (pop_score * 0.1)
                
                # 附加資訊
                store["hybrid_score"] = round(final_score, 4)
                store["semantic_similarity"] = round(sim_score, 4)
                ranked_list.append(store)

        # 根據總分排序，由高到低
        ranked_list.sort(key=lambda x: x["hybrid_score"], reverse=True)

        return ranked_list[:top_k]