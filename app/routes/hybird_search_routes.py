
# app/routes/hybrid_search_routes.py
from fastapi import APIRouter, HTTPException, Body
from app.repository.rdbms_repository import RdbmsRepository 
from app.repository.vector_repository import VectorRepository
from app.services.hybrid_SQL_builder_service_v2 import HybridSQLBuilder
from app.utils.performance_tracker import log_performance_to_csv
from app.services.vector_service import VectorService
from app.utils.data_formatter import format_response_data   # 格式化搜尋結果與補上照片
import logging
from app.utils.data_formatter import check_search_status,generate_diagnostics   # 產生除錯訊息
from app.utils.quality_checker import evaluate_search_quality
import time

place_search = APIRouter()

@place_search.post("/place_search")
async def generate_query_and_search(ai_to_api_data: dict = Body(...)): # 建議改名，因為現在不只 generate query，還有 search
        t0 = time.perf_counter()  # 整個請求開始
        

        # 獲取並檢查資料
        if not ai_to_api_data:
            # FastAPI 使用 raise HTTPException 來處理錯誤，這會自動轉換為 JSON 回傳給前端
            raise HTTPException(status_code=400, detail={"status": "fail", "message": "No data"})
        
        logging.info(f"fetched data: {ai_to_api_data}")

        try:
            # 初始化服務
            builder = HybridSQLBuilder()
            vector_service = VectorService()
            rdbms_repo = RdbmsRepository(use_mock=False) 

            # 針對輸入的json進行分析意圖
            plan = builder.analyze_intent(ai_to_api_data)

            # 先執行RDBMS的結構性資料搜尋(例如店家名稱,店家地址,店家電話,店家營業時間,店家距離,店家網站,店家總評論星等,店家營業狀態)(不帶向量 ID 限制)
            # 後續會增加店家價位的過濾功能
            # 這樣不管JSON有什麼欄位，都會先過濾出基本的餐廳名單
            final_sql, query_params = builder.build_sql(plan, vector_result_ids=None)

            #獲取sid進行每個sid的RDBMS的結構性資料搜尋的查詢程序,並記錄查詢參數與除錯訊息
            s_id = plan.get("s_id")


            # --- 階段一：SQL 查詢 (含自動降階) ---
            max_retries = 2
            rdb_info = {"status": "sql_no_data", "total_count": 0, "is_fallback": False}
            
            for attempt in range(max_retries):
                is_fallback_run = (attempt > 0)
                
                # 1. 生成 SQL (傳入 is_fallback 讓 Builder 知道要放寬)
                final_sql, query_params = builder.build_sql(plan, is_fallback=is_fallback_run)
                
                logging.info(f"[Search][SID: {s_id}] 執行 SQL (第 {attempt+1} 輪, Fallback={is_fallback_run})")
                db_results, _ = await rdbms_repo.execute_dynamic_query(final_sql, query_params, s_id)

                # 2. 生成並執行 Count SQL (同樣要帶入 is_fallback)
                count_sql, count_params = builder.build_count_sql(plan, is_fallback=is_fallback_run)
                count_results, _ = await rdbms_repo.execute_dynamic_query(count_sql, count_params, s_id)
                total_count = count_results[0]['total'] if count_results else 0

                # 3. 判斷是否有資料命中
                if total_count > 0:
                    rdb_info["total_count"] = total_count
                    rdb_info["is_fallback"] = is_fallback_run
                    
                    # 狀態分類：延續至後續判斷
                    if total_count == 1:
                        rdb_info["status"] = "exact_one_match" # 修改名稱以區別向量搜尋的 exact_match
                    else:
                        rdb_info["status"] = "success"
                    
                    logging.info(f"[Search][SID: {s_id}] 命中成功，脫離迴圈。")
                    break
                else:
                    logging.warning(f"[Search][SID: {s_id}] 第 {attempt+1} 輪查無結果...")
            
            # 迴圈結束後，如果 db_results 依然為空，rdb_info 會維持 "sql_no_data"


            # --- 執行搜尋與權重排序 ---
            # 這裡直接取代掉原本從 vector_ids_for_sql 到 db_results = db_results[:3] 的所有內容
            t_sql_done = time.perf_counter()
            sql_service_duration = t_sql_done - t0

            db_results, vector_search_info = await vector_service.search_and_rank(
                db_results=db_results,
                plan=plan,
                total_count=total_count,
                top_k=3
            )
            t_vector_done = time.perf_counter()

            # 從 vector_search_info 取得 service 內部的細分秒數
            qdrant_duration = vector_search_info.get("qdrant_time", 0)
            ranking_duration = vector_search_info.get("ranking_time", 0)
            
            # 過渡耗時 = (Vector 總耗時) - (Qdrant 淨耗時) - (指標排序淨耗時)
            transition_duration = (t_vector_done - t_sql_done) - qdrant_duration - ranking_duration


            # 上照片 (enrich_results_with_photos),
            # 如果 SQL 撈出來的是字串格式的 JSON（例如營業時間或設施標籤），它會把它轉成 Python 的字典（dict）或列表（list），方便前端直接讀取
            # 如果 facility_tags 被選取了，它會對這些標籤進行美化或過濾處理
            db_results = format_response_data(db_results, plan)

            # 取得搜尋狀態與診斷建議
            search_status = check_search_status(db_results, plan, total_count=total_count)

            # 對搜尋結果做一個搜尋結果品質的判斷
            quality_label, is_fallback, ai_hint = evaluate_search_quality(
                db_results, 
                vector_search_info, 
                rdb_info=rdb_info,
                plan=plan
            )

            t_end = time.perf_counter()
            total_duration_route = t_end - t0

            log_performance_to_csv({
                "sql_service": round(sql_service_duration, 4),
                "transition": round(transition_duration, 4),
                "qdrant": round(qdrant_duration, 4),
                "ranking": round(ranking_duration, 4),
                "total": round(total_duration_route, 4)
            })


            # 回傳精簡後的 Response 物件
            response = {
                "s_id": plan.get("s_id"),       # 用戶的s_id
                "status": quality_label,        # 狀態: success / partial_success / no_data
                "data": {
                        # 保底旗標
                        # 意義：是否觸發了「退而求其次」的邏輯
                        # 描述：True 代表結果並非 100% 符合 AI 解析出的語意關鍵字，是給 AI 判斷語氣的最快開關
                        # 用途1：對 AI (LLM)：作為**「信心判斷」**的快速開關。AI 看到 True 就應自動切換為「謙虛模式」，避免對搜尋結果過度承諾
                        # 用途2：對前端 UI：用於決定是否顯示**「相似推薦」或「精選替代」**的警示 UI 標籤，讓用戶知道搜尋結果並非精確匹配
                        "is_fallback": is_fallback,

                        # AI 行為指南
                        # 意義：後端對生成式模型的「口頭交代」
                        # 描述：根據搜尋品質生成的文字指令。AI 應將此內容納入 Context，決定要「邀功」還是「致歉」
                        # 用途1: 對 AI (LLM)：直接作為 System Message 的補充內容。模型會根據此文字決定對話策略（例如：當命中失敗時，主動致歉並解釋推薦邏輯；當命中成功時，則加強推薦力道）
                        # 用途2: 對除錯 (Debug)：讓開發者在不用進入向量庫查看分數的情況下，直接透過 API 回傳結果一眼看出「為什麼 AI 會用這種語氣說話」，這能大幅縮短優化 Prompt 的時間
                        "ai_behavior_hint": ai_hint, 

                        # 搜尋狀態診斷
                        # 意義：描述底層 SQL 與向量庫的匹配狀況
                        # 描述：例如 "skipped" (跳過向量), "no_match" (搜尋無果), "success" (搜尋成功)
                        # 用途：主要給後端除錯或前端顯示診斷訊息使用
                        "search_status": search_status,

                        # 向量搜尋元數據
                        # 意義：記錄向量資料庫（Qdrant/Milvus）的執行細節
                        # 內容：包含搜尋到的原始分數 (Score)、匹配的店家 ID 清單等
                        # 用途：用於驗證 AI 推薦的相似度權重是否合理
                        "vector_search_info": vector_search_info,

                        # 最終推薦清單
                        # 意義：經過 Hybrid Ranking 權重計算後，排序前三名的店家物件列表
                        # 內容：包含店家基本資訊、距離、星等、營業時間、以及計算出的混合分數 (hybrid_score)
                        # 描述：這是前端與用戶最終會看到的實體資料內容
                        "final_results": db_results
                }
            }

            return response

        except Exception as e:
            logging.error(f"Search API Error: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))