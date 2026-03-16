# app/services/vector_service.py
from typing import List, Dict, Any, Optional,Tuple
from app.repository.vector_repository import VectorRepository
from sentence_transformers import SentenceTransformer
from app.models.search_dto import VectorSearchResult
import math
import logging
import numpy as np
import math

class VectorService:
    def __init__(self):
        # 初始化倉管員
        self.repo = VectorRepository()
    # 檢查向量需求 - 向量搜尋 - 權重計算與排序
    async def search_and_rank(
        self, 
        db_results: List[Dict[str, Any]], 
        plan: Dict[str, Any], 
        total_count: int = 0,
        top_k: int = 3
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        
        info = {"status": "init", "message": "", "is_fallback": False}
        
        s_id = plan.get("s_id", "unknown_sid")
        keywords = plan.get("vector_keywords")

        logging.info(f"[Vector Service][SID: {s_id}] === 進入向量處理階段 ===")
        logging.info(f"[Vector Service][SID: {s_id}] 接收關鍵字 (keywords): {keywords}")
        logging.info(f"[Vector Service][SID: {s_id}] 候選店家筆數 (SQL Results): {len(db_results)}")

        # 攔截 Case 0: 完全查無店家
        if total_count == 0 or not db_results:
            logging.warning(f"[Vector Service][SID: {s_id}] Case 0: SQL 查無店家，直接中斷")
            info.update({
                "status": "sql_no_data", 
                "message": "資料庫中沒有符合關鍵字或營業狀態的店家。",
                "is_fallback": True
            })
            return [], info

        # 只要執行到這，代表一定有資料 (Case 1 or N)
        # 統一輸出抽樣日誌，幫助除錯 (包含店名、類別、標籤，建議加上距離)
        sample_data = [{ 
            "name": r.get('restaurant_name'), 
            "cat": r.get('merchant_categories'), 
            "dist": f"{r.get('distance', 0):.2f}km", # 加上距離更專業
            "tags": r.get('facility_tags') 
        } for r in db_results[:3]]
        
        logging.info(f"[Vector Service][SID: {s_id}] SQL 命中 {len(db_results)} 筆 (總數: {total_count})")
        logging.info(f"[Vector Service][SID: {s_id}] 候選範例: {sample_data}")
        

        # 建立一個映射字典，把英文 Key 對應回你 passage 裡使用的中文詞彙
        KEY_MAP = {
            "cuisine_type": "菜系",
            "food_type": "食物種類",
            "flavor": "口味",
            "service_tags": "服務標籤"
        }

        if isinstance(keywords, dict) and keywords:
            semantic_pairs = []
            target_values_list = []
            
            for k, v in keywords.items():
                # 把英文 key 轉成中文，如果找不到對應的，就先用原本的 key
                chinese_key = KEY_MAP.get(k, k) 
                
                # 格式：[中文特徵名]是[中文內容] -> 例如: "食物種類是火鍋"
                semantic_pairs.append(f"主打的{chinese_key}是{v}")
                target_values_list.append(str(v))
            
            # 結構化特徵字串: "主打的食物種類是火鍋，主打的口味是麻辣"
            feature_description = "，".join(semantic_pairs)
            target_values = "、".join(target_values_list)
            
            # 最終組合：高度對齊 passage 的語法，並加入使用者的強烈意圖
            query_str = (
                f"我想找一家餐廳，{feature_description}。"
                f"我想吃{target_values}，請推薦符合這些特色的美食。"
            )

        elif isinstance(keywords, list) and keywords:
            target_keywords = "、".join([str(i) for i in keywords])
            query_str = f"我想找關於{target_keywords}的餐廳。請推薦主打{target_keywords}的美食。"
            
        elif keywords:
            target_keywords = str(keywords)
            query_str = f"我想找{target_keywords}的餐廳。請推薦好吃的{target_keywords}。"
            
        else:
            query_str = "請推薦附近好吃的美食餐廳。"

        logging.info(f"[Vector Service][SID: {s_id}] 最終送往向量庫的字串: '{query_str}'")

        rdbms_ids = [row.get("id") for row in db_results]

        logging.info(f"[Vector Service][SID: {s_id}] 執行向量過濾搜尋 (SQL IDs 數量: {len(rdbms_ids)})")

        # 執行向量搜尋
        vector_results: Optional[List[VectorSearchResult]] = await self.repo.search_in_ids(query_str, rdbms_ids)
        if vector_results:
            logging.info(f"📊 [診斷][SID: {s_id}] 向量庫原始回傳前 5 筆分數: {[r.score for r in vector_results[:5]]}")
        else:
            logging.warning(f"❌ [診斷][SID: {s_id}] 向量庫回傳空結果，請確認 Qdrant 裡的 ID 是否與 SQL 對得上")
        
        # 定義相似度門檻
        SCORE_THRESHOLD = 0.4

        # 安全地取得最高分 (如果沒結果就給 0)
        best_score = vector_results[0].score if vector_results else 0.0

        # 4. 判斷搜尋結果是否失效 (無結果 或 分數低於門檻)
        if not vector_results or best_score < SCORE_THRESHOLD:
            # 根據不同情況給予 Log 訊息
            reason = "向量搜尋回傳 0 筆" if not vector_results else f"相似度太低 ({best_score:.4f})"

            
            logging.warning(f"[Vector Service][SID: {s_id}] {reason}，採用保底排序")
            
            info.update({
                "status": "vector_no_match", 
                "message": f"找不到足夠精確的匹配 (相關度: {best_score:.2f})，已切換為評價排序。",
                "is_fallback": True
            })
            # 直接跳過 Hybrid Ranking，執行保底排序 (回傳星等或距離最高的前三名)
            return self._apply_fallback_sorting(db_results, plan, top_k), info
        
        # --- 只有分數達標，才印出命中 Log 並執行 Hybrid Ranking ---
        logging.info(f"[Vector Service][SID: {s_id}] 向量庫命中 {len(vector_results)} 筆，最高原始分數: {best_score:.4f}")

        # 執行權重排序 (Hybrid Ranking)
        final_results = await self._apply_hybrid_ranking(vector_results, db_results, top_k, plan, info)
        
        # 成功後的日誌：這時候才有 final_results 可以印！
        if final_results:
            top_info = [f"{r.get('id')}({r.get('restaurant_name')})" for r in final_results[:3]]
            logging.info(f"[Vector Service][SID: {s_id}] 混合排序完成，前{top_k}名推薦: {', '.join(top_info)}")
        else:
            logging.warning(f"[Vector Service][SID: {s_id}] 混合排序後無匹配結果")

        return final_results, info
    
    # 根據向量查詢結果進行權重運算與排序
    async def _apply_hybrid_ranking(
        self, 
        vector_results: List[Any], 
        db_results: List[Dict[str, Any]], 
        top_k: int,
        plan: Dict[str, Any], 
        info: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        
        db_map = {str(row['id']): row for row in db_results}
        s_id = plan.get("s_id", "unknown")
        
        # 動態權重向量
        sort_conditions = plan.get("sort_conditions", [])
        weights = {"sim": 0.80, "rating": 0.15, "pop": 0.05, "dist": 0.0}
        sort_strategy = "預設語意優先"

        if sort_conditions:
            primary_sort = sort_conditions[0].get("field")
            if primary_sort == "distance":
                weights = {"sim": 0.40, "dist": 0.50, "rating": 0.10, "pop": 0.0}
                sort_strategy = "距離優先"
            elif primary_sort == "rating":
                weights = {"sim": 0.50, "rating": 0.40, "pop": 0.10, "dist": 0.0}
                sort_strategy = "評價優先"

        # 準備矩陣與數據
        valid_ids = []
        data_list = []
        
        all_counts = [row.get('user_ratings_total', 0) for row in db_results]
        max_reviews_log = math.log1p(max(all_counts)) if all_counts and max(all_counts) > 0 else 1.0

        for v in vector_results:
            v_id = str(v.id)
            if v_id in db_map:
                store = db_map[v_id]
                similarity_score = float(v.score)   # 取出該店的餘弦相似度並正規化
                rating_score = float(store.get('rating', 0)) / 5.0  # 取出該店的評論星等分數並正規化
                popularity_score = math.log1p(store.get('user_ratings_total', 0)) / max_reviews_log # 取出該店的人氣數並正規化
                
                dist_m = float(store.get("distance", 0))    # 取出該店的距離分數並正規化
                distance_score = 1.0 / (1.0 + (dist_m / 1000.0))    # 取出該店的距離分數並正規化
                
                data_list.append([similarity_score, rating_score, popularity_score, distance_score]) # 把每一家店家的四項指標存入矩陣
                valid_ids.append(v_id)

        if not data_list: return [] # 如果整個矩陣是空的那就回傳空陣列並結束程式

        matrix = np.array(data_list) # 把dist_list轉成numpy矩陣,也為了數據的純淨性
        w_vector = np.array([weights["sim"], weights["rating"], weights["pop"], weights["dist"]]) # 根據用戶需求決定的權重封裝成一個長度為 4 的向量。如: w = [w_{sim}, w_{rating}, w_{pop}, w_{dist}]
        eps = 1e-6 # 對剛開的店的補助,避免程式因為對0取對數富像無限大從而當機,此為10的-6次方
        
        # 核心運算：對數空間點積
        # 為了將線性空間的特徵值映射到對數流形 (Log-manifold)
        log_matrix = np.log(matrix + eps)
        
        # 我們不直接做 dot，而是用元素相乘 (Element-wise multiplication)
        # 這樣會得到一個 N x 4 的矩陣，裡面存著每個店家的每個維度實際加了多少分
        contribution_matrix = log_matrix * w_vector 
        
        # 總分依然是橫向加總
        total_log_scores = np.sum(contribution_matrix, axis=1)
        # 為了實現非線性的幾何聚合 (Non-linear Geometric Aggregation)
        # 沒有以下這一行其實只是換成矩陣運算的線性加權(跟之前的版本是一樣的效果)
        final_scores = np.exp(total_log_scores)  # 為了實現非線性的幾何聚合 (Non-linear Geometric Aggregation)
        seen_names = set() # 用於追蹤已排入的店名

        # 理由提取與結果封裝
        sorted_indices = np.argsort(final_scores)[::-1]
        
        # 定義理由模板
        reason_tags = ["語意最精準", "高分評價推薦", "人氣名店", "距離最近"]
        
        final_results = []
        for idx in sorted_indices:
            v_id = valid_ids[idx]
            store_entry = db_map[v_id].copy()
            name = store_entry.get("restaurant_name")

            # 如果這家店名已經出現過了，就跳過 (因為目前的 idx 是由高分排到低分，先入者必為最高分)
            if name in seen_names:
                continue
                
            # 找出這家店得分最高的維度索引
            best_dim_idx = np.argmax(contribution_matrix[idx])

            store_entry["applied_strategy"] = sort_strategy
            store_entry["ranking_reason"] = reason_tags[best_dim_idx]
            store_entry["hybrid_score"] = round(float(final_scores[idx]), 4)
            store_entry["semantic_similarity"] = round(matrix[idx][0], 4)
            
            store_entry["score_analysis"] = {
                "sim": round(matrix[idx][0], 2),
                "rating": round(matrix[idx][1], 2),
                "pop": round(matrix[idx][2], 2),
                "dist": round(matrix[idx][3], 2)
            }
            
            final_results.append(store_entry)
            seen_names.add(name) # 標記此店名已處理

            # 達到要求的數量就停止，節省後續計算
            if len(final_results) >= top_k:
                break

        logging.info(f"[Hybrid Rank][SID: {s_id}] 排序完成，已生成可解釋性理由。")
        return final_results

    # 當不需要執行向量搜尋，或是向量搜尋失效沒找到結果時
    # 確保系統依然能回傳一個對使用者有意義的「前三名」清單
    # 這裡要放TOPISIS的演算法邏輯
    def _apply_fallback_sorting(self, db_results, plan, top_k):
        res = db_results.copy() # 先複製一份，避免改到原始資料
        
        # 判斷使用者的意圖是否包含「距離」
        if plan.get("distance_needed"):
            # 如果使用者在意距離，就按距離由近到遠排 (從小到大)
            # 若沒距離資料，就給它無限大 (float('inf')) 丟到最後面
            res.sort(key=lambda x: x.get("distance", float('inf')))
        else:
            # 如果使用者沒要求距離，就按「星等評分」由高到低排 (從大到小)
            # 若沒星等資料，預設為 0
            res.sort(key=lambda x: x.get("rating", 0), reverse=True)
            
        return res[:top_k] # 最後只取前三名 (top_k=3)