# app/services/vector_service.py
from typing import List, Dict, Any, Optional,Tuple
from app.repository.vector_repository import VectorRepository
from sentence_transformers import SentenceTransformer
from app.models.search_dto import VectorSearchResult
import math
import logging
import numpy as np
import math
import time
import json


class RankSettings:
    ALLOWED_FIELDS = {"distance", "rating", "popularity", "similarity"}

    # 情況 A：完全沒條件時的「強偏好」
    DEFAULT_WEIGHTS = {
        "similarity": 0.80, "rating": 0.15, "popularity": 0.05, "distance": 0.0
    }

    # 情況 B：有條件時的「弱偏好基底」
    DYNAMIC_BASE = {
        "similarity": 0.3, "rating": 0.05, "popularity": 0.0, "distance": 0.0
    }

    PRIMARY_BONUS = 0.4
    SECONDARY_BONUS = 0.2


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
    
        # 獲取當次查詢的s_id用於紀錄詳細日誌
        # keywords: 紀錄當次查詢需要的所有語意搜尋關鍵字
        s_id = plan.get("s_id", "unknown_sid")
        keywords = plan.get("vector_keywords")

        # 初始化結果容器與狀態指標
        info = {"status": "init", "message": "", "is_fallback": False}
        soft_preferences = []       # 軟性語意標籤
        semantic_parts = []         # 用於構建 Embedding Query 的短句列表

        # 定義口語到標準標籤的映射
        TAG_MAPPING = {
            "有停車場": "特約停車場",  
            "冷氣": "冷氣",
            "外帶": "外帶",
            "內用": "內用"
        }


        if isinstance(keywords, dict):
            # 1. 獲取標籤（處理 List 或 String 避免覆蓋問題）
            raw_tags = keywords.get("service_tags", "")
            tags_to_join = []
            if isinstance(raw_tags, list):
                tags_to_join = raw_tags
            elif raw_tags:
                tags_to_join = [raw_tags]
            
            if tags_to_join:
                # 合併標籤，並將全形頓號轉為空格以利語意理解
                tags_str = " ".join(tags_to_join).replace("、", " ")
                semantic_parts.append(f"希望能有這些特色：{tags_str}。")

            # 2. 定義語意查詢模板（只需定義一次）
            # 優先級：菜系 > 食物 > 口味
            mapping_fields = [
                ("cuisine_type", "菜系風格", "推薦{}風味的餐廳。"),
                ("food_type", "主打美食", "我想找關於{}的店家。"),
                ("flavor", "口味要求", "這家店的食物吃起來是{}口味的。")
            ]

            # 3. 執行迴圈構建語意句子
            for field, prefix, template in mapping_fields:
                val = keywords.get(field)
                if val:
                    # 如果 val 是來自 LLM 的複數節點 (List)，將其合併
                    val_str = " ".join(val) if isinstance(val, list) else str(val)
                    # 這裡可以選擇要用 template 還是 prefix，建議 template 語意較強
                    semantic_parts.append(template.format(val_str))

            # 4. 處理軟性偏好
            if soft_preferences:
                soft_tags_str = " ".join(soft_preferences).replace("、", " ")
                semantic_parts.append(f"環境具備{soft_tags_str}等特色。")

        # 5. 組合最終查詢字串（這行要縮排回 function 層級，不要在 if keywords 裡面）
        query_str = " ".join(semantic_parts) or "推薦優質的美食餐廳"
            
        logging.info(f"[Vector Service] 模糊語意查詢: '{query_str}'")

        logging.info(f"[Vector Service][SID: {s_id}] === 進入向量處理階段 ===")
        logging.info(f"[Vector Service][SID: {s_id}] 接收關鍵字 (keywords): {keywords}")
        logging.info(f"[Vector Service][SID: {s_id}] 候選店家筆數 (SQL Results): {len(db_results)}")

        # 只要執行到這，代表一定有資料 (Case 1 or N)
        # 統一輸出抽樣日誌，幫助除錯 (包含店名、類別、標籤，建議加上距離)
        sample_data = [{ 
            "name": r.get('restaurant_name'), 
            "cat": r.get('merchant_category'), 
            "dist": f"{r.get('distance', 0):.2f}km", # 加上距離更專業
            "tags": r.get('facility_tags') 
        } for r in db_results[:3]]
        
        logging.info(f"[Vector Service][SID: {s_id}] SQL 命中 {len(db_results)} 筆 (總數: {total_count})")
        logging.info(f"[Vector Service][SID: {s_id}] 候選範例: {sample_data}")
        logging.info(f"[Vector Service][SID: {s_id}] 最終送往向量庫的字串: '{query_str}'")

        # 關聯式資料庫的店家搜尋結果列表,準備要丟入向量進行範圍搜尋
        rdbms_ids = [row.get("id") for row in db_results] 

        # 如果沒語意需求，也不需要硬性過濾標籤，就走純排序
        is_pure_sorting = not semantic_parts 

        if is_pure_sorting:
            logging.info(f"[Vector Service][SID: {s_id}] 無明確語意需求，進入 [純指標排序模式]")
            # 模擬滿分向量結果，讓後續矩陣運算完全由 RDBMS 指標 (評分、距離) 主導
            vector_results = [
                VectorSearchResult(id=row.get("id"), score=1.0) 
                for row in db_results
            ]
            best_score = 1.0
            CURRENT_THRESHOLD = 0.0
        else:
            # 只有在「有需求」時才真正呼叫向量資料庫
            logging.info(f"[Vector Service][SID: {s_id}] 語意查詢字串: '{query_str}'")
            logging.info(f"[Vector Service][SID: {s_id}] 執行向量過濾搜尋 (SQL IDs 數量: {len(rdbms_ids)})")
            
            q_start = time.perf_counter()
            vector_results = await self.repo.search_in_ids(
                query_str, 
                rdbms_ids, 
                base_amenities=None
            )
            q_end = time.perf_counter()
            info["qdrant_time"] = q_end - q_start
    
            # 動態調整門檻,根據用戶查詢複雜度
            CURRENT_THRESHOLD = self._calculate_dynamic_threshold(keywords, soft_preferences)
            
            best_score = vector_results[0].score if vector_results else 0.0
            
            logging.info(f"[Vector Service][SID: {s_id}] 動態門檻已設定為: {CURRENT_THRESHOLD:.2f}")


        # --- 3. 統一門檻檢查 ---
        if not vector_results or best_score < CURRENT_THRESHOLD:
            reason = "向量搜尋回傳 0 筆" if not vector_results else f"相似度太低 ({best_score:.4f})"
            logging.warning(f"[Vector Service][SID: {s_id}] {reason}，已全數過濾（不執行降階）")
            
            info.update({
                "status": "vector_no_match", 
                "message": "抱歉，附近目前沒有找到符合您描述的店家。",
                "is_fallback": False
            })
            # 關鍵修改：直接回傳空列表，不拿 SQL 的前三名來墊檔
            return [], info

        # --- 4. 執行權重排序 (Hybrid Ranking) ---
        logging.info(f"[Vector Service][SID: {s_id}] 進入混合排序階段，候選數: {len(vector_results)}")
        r_start = time.perf_counter()
        final_results = await self._apply_hybrid_ranking(
            vector_results, db_results, top_k, plan, info, CURRENT_THRESHOLD
        )
        r_end = time.perf_counter()
        info["ranking_time"] = r_end - r_start
        
        return final_results, info
    

    
    def _calculate_dynamic_threshold(
        self, 
        keywords: Any, 
        soft_preferences: List[str]
    ) -> float:
        """
        動態門檻全語意版：
        1. 取消硬性標籤參數，改為判斷 service_tags 是否存在。
        2. 針對語意維度給予複雜度補償。
        3. 保留語意寬容度，確保多條件下不會因為相似度稀釋而全數過濾。
        """
        # 降低基礎起點，從 0.35 降到 0.30
        BASE_THRESHOLD = 0.30  
        
        # 1. 計算維度複雜度 (active_dims)
        active_dims = 0
        has_service_tags = False
        
        if isinstance(keywords, dict):
            if keywords.get("cuisine_type"): active_dims += 1
            if keywords.get("food_type"): active_dims += 1
            if keywords.get("flavor"): active_dims += 1
            
            # 判斷是否有服務標籤（這是新邏輯）
            if keywords.get("service_tags"):
                has_service_tags = True
                active_dims += 1
                
        if soft_preferences: 
            active_dims += 1

        # 2. 針對「過於簡單」的查詢進行特殊處理
        # 當維度非常少時（例如只搜單一關鍵字），相似度通常分布較廣且低，給予較大補償
        if active_dims <= 1:
            complexity_bonus = 0.08
        else:
            complexity_bonus = active_dims * 0.02
        
        # 3. 語意細節補償 (取代原本的硬性標籤補償)
        # 如果使用者有指定 service_tags 或 soft_preferences，代表意圖豐富，稍微降低門檻以防過濾過頭
        tag_bonus = 0.04 if (has_service_tags or soft_preferences) else 0.0
        
        # 4. 計算最終門檻並設定保底值
        # 設定一個較寬鬆的絕對下限 0.22，讓 BGE-M3 在處理模糊查詢時更有彈性
        final_threshold = max(0.22, BASE_THRESHOLD - complexity_bonus - tag_bonus)
        
        logging.info(
            f"[Threshold Optimizer] 維度數: {active_dims}, "
            f"複雜度獎勵: {complexity_bonus:.2f}, 標籤細節補償: {tag_bonus:.2f}, "
            f"最終門檻: {final_threshold:.2f}"
        )
        
        return final_threshold
    

    # 根據向量查詢結果進行權重運算與排序
    async def _apply_hybrid_ranking(
        self, 
        vector_results: List[VectorSearchResult],
        db_results: List[Dict[str, Any]], 
        top_k: int,
        plan: Dict[str, Any], 
        info: Dict[str, Any],      
        semantic_threshold: float 
    ) -> List[Dict[str, Any]]:
        
        db_map = {str(row['id']): row for row in db_results}
        vector_map = {str(v.id): v for v in vector_results}
        s_id = plan.get("s_id", "unknown")

        # LLM 有時候會給一些垃圾標籤，這邊先擋掉以免後面崩潰
        sort_conditions = plan.get("sort_conditions", [])
        # Filter out trash tags
        valid_conditions = [
            cond.get("field") for cond in sort_conditions 
            if isinstance(cond, dict) and cond.get("field") in RankSettings.ALLOWED_FIELDS
        ]


        if not valid_conditions:
            weights = RankSettings.DEFAULT_WEIGHTS.copy()
            sort_strategy = "預設語意優先"
        else:
            weights = RankSettings.DYNAMIC_BASE.copy()
            sort_strategy = f"條件排序 ({', '.join(valid_conditions)})"
            
            # 動態分配累加
            # the competition
            for idx, field in enumerate(valid_conditions):
                bonus = RankSettings.PRIMARY_BONUS if idx == 0 else RankSettings.SECONDARY_BONUS
                weights[field] = weights.get(field, 0.0) + bonus

        # 總和必須是 1，不然 NumPy 的 exp 會算到起飛
        total_w = sum(weights.values())
        if total_w > 0:
            # 因為 round(..., 2) 有時候會讓總和變成 0.99 或 1.01。雖然對 np.exp 影響不大，
            # 為了數據純淨把round(...,2)拿掉
            weights = {k: v / total_w for k, v in weights.items()}
        else:
            weights = RankSettings.DEFAULT_WEIGHTS.copy()

        logging.info(f"[Hybrid Rank][SID: {s_id}] 採用策略: {sort_strategy}, 最終權重分配: {weights}")


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

        if len(data_list) == 0:
            logging.error(f"[Rank] SID:{s_id} 沒資料可以排!檢查一下 SQL 或向量庫。")
            return []

        # 把dist_list轉成numpy矩陣,也為了數據的純淨性
        # 根據用戶需求決定的權重封裝成一個長度為 4 的向量。如: w = [w_{sim}, w_{rating}, w_{pop}, w_{dist}]
        matrix = np.array(data_list) 
        weights_vec = np.array([
            weights["similarity"], 
            weights["rating"], 
            weights["popularity"], 
            weights["distance"]
        ])
        

        eps = 1e-6 # 這是為了防止對數運算遇到 0 崩潰加的保險
        
        # 核心運算：對數空間點積
        # 為了將線性空間的特徵值映射到對數流形 (Log-manifold)
        log_matrix = np.log(matrix + eps)
        
        # 不直接做 dot，而是用元素相乘 (Element-wise multiplication)
        # 這樣會得到一個 N x 4 的矩陣，裡面存著每個店家的每個維度實際加了多少分
        contribution_matrix = log_matrix * weights_vec
        
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

            sim_score = matrix[idx][0]
            if sim_score < semantic_threshold:
                logging.debug(f"[Hybrid Rank] ID: {v_id} 語意分數 {sim_score:.4f} 不及格，直接淘汰。")
                continue # 跳過這家店，不加入推薦名單！
            
            store_entry = db_map[v_id].copy()

            raw_tags = store_entry.get("facility_tags")

            logging.info(f"[DEBUG] ID:{v_id} 原始 raw_tags 型態: {type(raw_tags)} 內容: {raw_tags}")

            if raw_tags:
                if isinstance(raw_tags, str):
                    try:
                        # 必須把解析後的結果「指定回」字典
                        store_entry["facility_tags"] = json.loads(raw_tags)
                    except:
                        # 解析失敗時，保留原始字串供除錯，或設為空列表
                        store_entry["facility_tags"] = [] 
                # 如果已經是 list 就維持原樣
            else:
                # 如果 raw_tags 是 None 或空字串
                store_entry["facility_tags"] = []

            if v_id in vector_map:
                store_entry["review_summary"] = vector_map[v_id].review_summary

            name = store_entry.get("restaurant_name")

            # 如果這家店名已經出現過了，就跳過 (因為目前的 idx 是由高分排到低分，先入者必為最高分)
            if name in seen_names:
                continue
                
            # 找出這家店得分最高的維度索引
            
            # 把權重為 0.0 的維度，分數設為極小的負數 (-999.0)，讓它絕對不可能成為最大值
            #for i, w in enumerate(weights_vec):
            #    if w == 0.0:
            #        masked_contribution[i] = -999.0 
            mask = (weights_vec == 0.0)
            row_contribution = contribution_matrix[idx].copy()  ## 找出這家店得分最高的維度索引
            row_contribution[mask] = -999.0  # 屏蔽掉沒權重的維度
            best_dim_idx = np.argmax(row_contribution)
                    

            store_entry["applied_strategy"] = sort_strategy
            store_entry["ranking_reason"] = reason_tags[best_dim_idx]
            store_entry["hybrid_score"] = round(float(final_scores[idx]), 4)
            store_entry["semantic_similarity"] = round(matrix[idx][0], 4)
            
            store_entry["score_analysis"] = {
                "similarity": round(matrix[idx][0], 2),
                "rating": round(matrix[idx][1], 2),
                "popularity": round(matrix[idx][2], 2),
                "distance": round(matrix[idx][3], 2)
            }
            
            final_results.append(store_entry)
            seen_names.add(name) # 標記此店名已處理

            # 達到要求的數量就停止，節省後續計算
            if len(final_results) >= top_k:
                break

        logging.info(f"[Hybrid Rank][SID: {s_id}] 排序完成，已生成可解釋性理由。")
        return final_results


if __name__ == "__main__":
    import asyncio
    
    # 簡單配置一下 Logging，不然你看不到那些酷酷的輸出
    logging.basicConfig(level=logging.INFO, format='%(message)s')

    async def test_run():
        service = VectorService()
        
        # 1. 模擬資料庫撈出來的店家 (RDBMS Results)
        mock_db_results = [
            {"id": 1, "restaurant_name": "老王拉麵", "rating": 4.5, "user_ratings_total": 1000, "distance": 500},
            {"id": 2, "restaurant_name": "小李便當", "rating": 3.2, "user_ratings_total": 50, "distance": 100},
            {"id": 3, "restaurant_name": "極黑和牛燒肉", "rating": 4.8, "user_ratings_total": 500, "distance": 2000},
        ]
        
        # 2. 模擬 LLM 產生的計畫 (Plan)
        # 測試場景：使用者想要「距離優先」
        mock_plan = {
            "s_id": "test_001",
            "vector_keywords": {
                "cuisine_type": "日式",
                "service_tags": "有停車場、冷氣"
            },
            "sort_conditions": [
                {"field": "distance", "direction": "asc"},
                {"field": "rating", "direction": "desc"}
            ]
        }

        print("\n🚀 [開始測試] 模擬搜尋與混合排序邏輯...")
        
        # 執行測試
        # 注意：因為測試環境沒接真的 VectorDB，你的 repo.search_in_ids 可能會報錯
        # 建議測試時可以先將 search_in_ids 內容暫時 mock 掉，或確保連線正常。
        try:
            results, info = await service.search_and_rank(
                db_results=mock_db_results,
                plan=mock_plan,
                top_k=3
            )

            print("\n✅ [排序結果回傳]")
            for i, r in enumerate(results):
                print(f"第 {i+1} 名: {r['restaurant_name']} | "
                      f"理由: {r['ranking_reason']} | "
                      f"總分: {r['hybrid_score']} | "
                      f"距離: {r['score_analysis']['distance']}")
            
            print(f"\n📊 [權重分配檢查]: {info.get('status')}")

        except Exception as e:
            print(f"❌ 測試失敗: {e}")
            print("提示：如果報錯是在 repo.search_in_ids，代表你可能沒開 Qdrant 或連不到 DB。")

    # 啟動非同步測試迴圈
    asyncio.run(test_run())