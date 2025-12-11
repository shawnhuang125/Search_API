from flask import Blueprint, request, jsonify
from app.services.hybird_SQL_builder_service_v2 import HybridSQLBuilder
from app.repository.rdbms_repository import RdbmsRepository 
from app.repository.vector_repository import VectorRepository
from app.services.hybird_SQL_builder_service_v2 import enrich_results_with_photos
import logging

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
        rdbms_repo = RdbmsRepository(use_mock=True)   # 使用模擬關聯式資料庫

        # 針對輸入的json進行分析意圖
        plan = builder.analyze_intent(ai_to_api_data)

        vector_ids_for_sql = None 
        vector_search_details = [] # 用來存詳細資料給前端看

        # 執行向量搜尋, 為了拿到 ID
        if plan["vector_needed"]:
            # 這裡會回傳模擬的 VectorSearchResult 物件列表
            raw_results = vector_repo.search_by_vector(plan["vector_keywords"][0]) # 假設取第一個關鍵字
            
            # 提取 ID 給 SQL Builder
            vector_ids_for_sql = [item.id for item in raw_results]
            
            # 提取詳細資料給 API 回傳 (方便除錯/顯示)
            vector_search_details = [vars(item) for item in raw_results]

        # 生成 SQL
        final_sql, query_params = builder.build_sql(plan, vector_result_ids=vector_ids_for_sql)

        # 3. 查詢 RDBMS (接入模擬資料的核心步驟)
        # 這會去呼叫 RdbmsRepository._execute_mock_db
        db_results = rdbms_repo.execute_dynamic_query(final_sql, query_params)

        db_results = enrich_results_with_photos(db_results, plan)

        # 回傳完整結果
        response = {
            "status": "success",
            "mode": "dry_run_with_mock_data", # 標示為含模擬資料的試跑
            "data": {
                # A. 向量搜尋的結果 (Metadata)
                "vector_search_info": {
                    "keywords": plan["vector_keywords"],
                    "found_ids": vector_ids_for_sql,
                    "details": vector_search_details
                },
                # B. 生成的 SQL
                "generated_query": {
                    "sql": final_sql,    
                    "params": query_params
                },
                # C. RDBMS 模擬查詢回來的資料 (這就是你要的 Mock Data!)
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