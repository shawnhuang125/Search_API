from flask import Blueprint, request, jsonify
from app.repository.rdbms_repository import RdbmsRepository 
from app.repository.vector_repository import VectorRepository
from app.services.hybrid_SQL_builder_service_v2 import HybridSQLBuilder
import logging
from app.utils.data_formatter import parse_json_fields, format_distance_display, check_search_status
from app.utils.get_photo import enrich_results_with_photos

place_search_bp = Blueprint("place_search_bp", __name__)

@place_search_bp.route("/search", methods=["POST"])
def generate_query_and_search(): # 建議改名，因為現在不只 generate query，還有 search
    # 獲取並檢查資料
    ai_to_api_data = request.get_json(force=True)
    if not ai_to_api_data:
        return jsonify({"status":"fail", "message":"No data"}), 400
    
    logging.info(f"fetched data: {ai_to_api_data}")

    try:
        # 初始化服務,開啟 use_mock=True 來測試流程
        builder = HybridSQLBuilder()
        vector_repo = VectorRepository(use_mock=True) # 使用模擬向量庫
        rdbms_repo = RdbmsRepository(use_mock=False)   # 使用模擬關聯式資料庫

        # 針對輸入的json進行分析意圖
        plan = builder.analyze_intent(ai_to_api_data)

        # 3. 第一步：先執行 RDBMS 搜尋 (不帶向量 ID 限制)
        # 這樣不管 JSON 有什麼欄位，都會先過濾出基本的餐廳名單
        final_sql, query_params = builder.build_sql(plan, vector_result_ids=None)
        db_results, sql_duration = rdbms_repo.execute_dynamic_query(final_sql, query_params)

        # 3. [新增] 執行總數查詢
        count_sql, count_params = builder.build_count_sql(plan, vector_result_ids=None)
        count_results, _ = rdbms_repo.execute_dynamic_query(count_sql, count_params)
        # 取得總數，若無結果則預設為 0
        total_count = count_results[0]['total'] if count_results else 0

        #logging.info(f"[Debug] 原始 DB 回傳類型: {type(db_results)}, 內容: {db_results[:1]}")
        # --- 呼叫封裝好的格式化工具，將判斷邏輯移出 Route ---
        from app.utils.data_formatter import format_response_data
        db_results = format_response_data(db_results, plan)

        vector_ids_for_sql = None 
        vector_search_info = {
            "status": "skipped",
            "message": "No vector search needed for this intent",
            "details": []
        }

        # 執行向量搜尋
        if plan.get("vector_needed"):
            #raw_results = vector_repo.search_by_vector(plan["vector_keywords"][0]) # 假設取第一個關鍵字
            is_vector_supported = False # 先寫死，直到資料準備好
            if not is_vector_supported:
                vector_search_info["status"] = "not_supported"
                vector_search_info["message"] = "向量資料庫 Payload 尚未就緒，已跳過語意比對，僅回傳精確匹配結果。"
                logging.warning("[Search] 向量功能未就緒，跳過比對")
            else:
                # 如果以後支援了，邏輯如下：
                # rdbms_ids = [row.get("id") for row in db_results]
                # raw_results = vector_repo.search_in_ids(plan["vector_keywords"][0], rdbms_ids)
                # vector_search_info["status"] = "success"
                # vector_search_info["details"] = [vars(item) for item in raw_results]
                pass
        # 4. 取得搜尋狀態 (此處會包含強化後的診斷建議)
        search_status = check_search_status(db_results, plan, total_count=total_count)
        # --- 關鍵改動：建立 diagnostics 區塊 ---
        diagnostics = None
        if not db_results:
            diagnostics = {
                "active_filters": query_params,  # 顯示實際帶入 SQL 的參數 (如 p0, p1)
                "reason": "目前過濾條件組合過於嚴苛，導致資料庫無相符結果",
                "debug_logic_tree": plan.get("raw_logic_tree"), # 顯示原始邏輯樹以便比對
                "sql_fragment": plan.get("generated_where_clause") # 建議在 builder 中存入此片段
            }
        
        # 回傳完整結果
        response = {
            "status": "success",
            "mode": "real_db_connection",
            "data": {
                "search_status": search_status,
                "diagnostics": diagnostics,   # 顯示詳細的錯誤訊息
                "vector_search_info": vector_search_info,  # 說明本次搜尋不做向量搜尋
                "generated_query": {
                    "sql": final_sql,    
                    "params": query_params
                },
                "performance": {
                    "sql_execution_time_sec": round(sql_duration, 4) # 取小數點後4位比較好看
                },
                "final_results": db_results 
            }
        }

        return jsonify(response), 200

    except Exception as e:
        logging.error(f"Search API Error: {e}", exc_info=True)
        return jsonify({
            "status": "fail",
            "message": "Internal Error",
            "error": str(e)
        }), 500