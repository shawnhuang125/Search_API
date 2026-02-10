from typing import List, Dict, Any, Optional
from app.repository.vector_repository import VectorRepository
from sentence_transformers import SentenceTransformer
from app.models.search_dto import VectorSearchResult
import math
import logging

class VectorService:
    def __init__(self):
        # 初始化倉管員
        self.repo = VectorRepository()
    # 檢查向量需求 - 向量搜尋 - 權重計算與排序
    async def search_and_rank(
        self, 
        keywords: Any, 
        db_results: List[Dict[str, Any]], 
        plan: Dict[str, Any], 
        top_k: int = 3
    ) -> Optional[List[Dict[str, Any]]]:
        
        s_id = plan.get("s_id", "unknown_sid")
        info = {"status": "skipped", "message": "No vector search needed", "details": []}

        logging.info(f"[Vector Service][SID: {s_id}] === 進入向量處理階段 ===")
        logging.info(f"[Vector Service][SID: {s_id}] 接收關鍵字 (keywords): {keywords}")
        logging.info(f"[Vector Service][SID: {s_id}] 候選店家筆數 (SQL Results): {len(db_results)}")

        if db_results:
            # 抽樣前 3 筆顯示店家屬性，幫助除錯為什麼沒有火鍋
            sample_data = [{ "name": r.get('restaurant_name'), "cat": r.get('merchant_categories'), "tags": r.get('facility_tags') } for r in db_results[:3]]
            logging.info(f"[Vector Service][SID: {s_id}] SQL 候選範例 (前3筆): {sample_data}")

        info = {"status": "skipped", "message": "No vector search needed", "details": []}
        
        # 1. 檢查是否沒有向量需求
        if not plan.get("vector_needed") or not db_results:
            logging.info(f"[Vector Service][SID: {s_id}] 不需要向量搜尋，進入保底排序")
            return self._apply_fallback_sorting(db_results, plan, top_k), info

        # 將字典內容轉換為鍵值對字串，例如 {"food_type": "火鍋"} -> "food_type 火鍋"
        if isinstance(keywords, dict) and keywords:
            # 建立結構化描述：這能幫助模型更精確定位特定欄位的特徵
            kv_pairs = [f"{k} {v}" for k, v in keywords.items()]
            kv_str = " ".join(kv_pairs)
            
            # 提取主要價值（如火鍋）來建構自然語言 Prompt
            main_values = ", ".join(keywords.values())
            query_str = f"尋找符合 {kv_str} 特徵的店家，我想吃 {main_values}，這是一間專門提供 {main_values} 的餐廳"
        elif isinstance(keywords, list) and keywords:
            query_str = f"我想吃 {', '.join(keywords)}，這是一間 {', '.join(keywords)} 餐廳"
        elif keywords:
            query_str = f"我想吃 {keywords}，這是一間 {keywords} 餐廳"
        else:
            query_str = "推薦美食餐廳"

        logging.info(f"[Vector Service][SID: {s_id}] 最終送往向量庫的字串: '{query_str}'")

        rdbms_ids = [row.get("id") for row in db_results]

        logging.info(f"[Vector Service][SID: {s_id}] 執行向量過濾搜尋 (SQL IDs 數量: {len(rdbms_ids)})")

        # 3. 執行向量搜尋
        vector_results: Optional[List[VectorSearchResult]] = await self.repo.search_in_ids(query_str, rdbms_ids)
        
        # 4. 判斷搜尋結果是否為空 (這裡做一次動作就好)
        if not vector_results:
            logging.warning(f"[Vector Service][SID: {s_id}] 向量搜尋回傳 0 筆，採用保底排序")
            info.update({"status": "no_match", "message": "向量搜尋未找到結果，採用保底排序"})
            return self._apply_fallback_sorting(db_results, plan, top_k), info
        
        # --- [新增] 向量命中 Log ---
        logging.info(f"[Vector Service][SID: {s_id}] 向量庫命中 {len(vector_results)} 筆，最高原始分數: {vector_results[0].score if vector_results else 'N/A'}")

        # 5. 執行權重排序 (Hybrid Ranking)
        final_results = await self._apply_hybrid_ranking(vector_results, db_results, top_k, plan, info)
        
        # 6. 成功後的日誌：這時候才有 final_results 可以印！
        if final_results:
            top_info = [f"{r.get('id')}({r.get('restaurant_name')})" for r in final_results[:3]]
            logging.info(f"[Vector Service][SID: {s_id}] 混合排序完成，前三名推薦: {', '.join(top_info)}")
        else:
            logging.warning(f"[Vector Service][SID: {s_id}] 混合排序後無匹配結果")

        return final_results, info
    
    # 根據向量查詢結果進行權重運算與排序
    async def _apply_hybrid_ranking(
        self, 
        vector_results: List[VectorSearchResult], 
        db_results: List[Dict[str, Any]], 
        top_k: int,
        plan: Dict[str, Any], 
        info: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        
        

        # 將 db_results 轉為 map 方便快速比對
        db_map = {str(row['id']): row for row in db_results}
        
        # 找出最大評論數用於歸一化 (避免除以零)
        all_counts = [row.get('user_ratings_total', 0) for row in db_results]
        max_val = max(all_counts) if all_counts else 1
        max_reviews_log = math.log1p(max_val) if max_val > 0 else 1
        
        # 動態配置權重
        #　如果有距離排序需求
        if plan.get("distance_needed", False):
            # 即使需要距離，語意權重也要拉高，否則會推薦「超近但完全不相關」的店
            weights = {"sim": 0.5, "rating": 0.1, "pop": 0.1, "dist": 0.3}
        else:
            # 預設模式：將語意相似度設為絕對主導，確保「火鍋」是第一優先
            weights = {"sim": 0.8, "rating": 0.1, "pop": 0.1, "dist": 0.0}

        ranked_list = []
        best_stores = {}

        match_count = 0  #除錯用

        for v in vector_results:
            v_id = str(v.id)
            if v_id in db_map:
                match_count += 1
                store = db_map[v_id].copy()
                
                # 語意相似度 (0.0 - 1.0)
                sim_score = v.score
                
                # 星等分數 (0-1)
                rating_score = float(db_map[v_id].get('rating', 0)) / 5.0
                
                # 人氣分數 (對數歸一化)
                reviews_count = store.get('user_ratings_total', 0)
                pop_score = math.log1p(db_map[v_id].get('user_ratings_total', 0)) / max_reviews_log

                # 距離
                dist_score = 0
                if plan.get("distance_needed") and "distance" in store:
                    # 從資料庫拿到的 dist_val 單位是「公尺」 (如 800, 1500)
                    dist_val = store.get("distance", 0)
                    
                    # --- 關鍵修正：將公尺轉為公里 ---
                    # 這樣 100m 會變成 0.1km -> 1/(1+0.1) = 0.90 分
                    # 這樣 1000m 會變成 1.0km -> 1/(1+1.0) = 0.50 分
                    dist_km = dist_val / 1000.0
                    
                    # 使用 1/(1+d) 公式，d 越小分數越高
                    dist_score = 1 / (1 + dist_km)

                # --- 2. 混合總分計算 ---
                current_score = (
                    (sim_score * weights["sim"]) + 
                    (rating_score * weights["rating"]) + 
                    (pop_score * weights["pop"]) + 
                    (dist_score * weights["dist"])
                )
                current_score = round(current_score, 4)

                # 如果這家店還沒進榜，或是這則評論算出的總分比之前的高，就更新它
                if v_id not in best_stores or current_score > best_stores[v_id]["hybrid_score"]:
                    # 從之前整理好的資料庫地圖（db_map）中抓出這家店的原始資料
                    # 複製一份資料避免污染原始 db_results
                    store_entry = db_map[v_id].copy()
                    # 將剛剛計算出來的「混合權重分數」（包含相似度、星等、距離、人氣的總分）
                    # 塞進這家店的資料欄位中
                    store_entry["hybrid_score"] = current_score
                    # 額外存下「語意相似度」，
                    # 這對於後續除錯或顯示「推薦原因」很有幫助（代表這家店在內容上多接近使用者的要求）
                    store_entry["semantic_similarity"] = round(sim_score, 4)
                    # 份完美的資料存入 best_stores 字典中。如果原本已經有舊資料，
                    # 這行會直接覆蓋（更新為更高分的版本）
                    best_stores[v_id] = store_entry
                
                

        logging.info(f"[Hybrid Rank] 最終比對成功數量: {match_count} / {len(vector_results)}")

        # 把字典轉成List
        # 用 .values() 把裡面所有的店家資料抓出來，轉成一個乾淨的 List
        ranked_list = list(best_stores.values())
        # 排列(由高到低)
        # 根據hybrid_score總權重值來排
        ranked_list.sort(key=lambda x: x["hybrid_score"], reverse=True)
        # 切片取件（只要前三名）
        # 即便資料庫搜尋出 100 幾家店,我們不希望一次塞給使用者看這麼多。
        # 這行代碼會從排序好的名單,從第0個位置切到第top_k 個(設定3)
        # 只拿走分數最高的那三家
        final_results = ranked_list[:top_k]

        # 做完完整的RAG查詢後,更新 info
        info.update({
            "status": "success",
            "message": f"完成混合排序，篩選前 {top_k} 名",
            "details": [{"id": r["id"], "score": r.get("hybrid_score")} for r in final_results]
        })

        return ranked_list[:top_k]
    
    # 當不需要執行向量搜尋，或是向量搜尋失效沒找到結果時
    # 確保系統依然能回傳一個對使用者有意義的「前三名」清單
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