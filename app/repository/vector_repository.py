from typing import List, Dict, Any, Optional
import logging
from app.models.search_dto import VectorSearchResult

# --- 未來階段：Qdrant 與 向量模型套件 ---
# try:
#     from qdrant_client import QdrantClient
#     from sentence_transformers import SentenceTransformer
# except ImportError:
#     logging.warning("尚未安裝 qdrant-client 或 sentence-transformers")

class VectorRepository:
    def __init__(self, host: str = "localhost", port: int = 6333, use_mock: bool = True):
        """
        初始化 Repository
        :param host: Qdrant 主機位址 (Default: localhost)
        :param port: Qdrant port (Default: 6333)
        :param use_mock: True = 使用模擬資料, False = 連線真實 DB
        """
        self.use_mock = use_mock
        self.collection_name = "restaurants"  # 未來 Qdrant 裡的 Collection 名稱

        # --- 設定檔與連線初始化 ---
        if self.use_mock:
            logging.info("[Repo] 初始化模式: MOCK DATA (模擬資料)")
            self.client = None
            self.model = None
        else:
            logging.info(f"[Repo] 初始化模式: REAL QDRANT (連線至 {host}:{port})")
            # --- 未來階段：解除註解以啟用真實連線 ---
            # self.client = QdrantClient(host=host, port=port)
            
            # 載入 Embedding 模型 (這會花一點時間，建議在啟動時做)
            # logging.info("正在載入 Embedding 模型 (all-MiniLM-L6-v2)...")
            # self.model = SentenceTransformer('all-MiniLM-L6-v2')
            # logging.info("模型載入完成")
            pass

    def search_by_vector(self, keywords: str) -> List[VectorSearchResult]:
        logging.info(f"[Repo] 執行向量搜尋, 關鍵字: {keywords}")

        # ==========================================
        #  分支 A: 使用真實 Qdrant (未來切換)
        # ==========================================
        if not self.use_mock:
            # 這裡放置未來的真實邏輯
            # return self._search_qdrant_logic(keywords)
            logging.warning("尚未實作真實連線，暫時切回 Mock 模式")
            pass

        # ==========================================
        #  分支 B: 使用模擬資料 (目前使用)
        # ==========================================
        logging.info(f"[Repo] 使用 Mock Data 進行過濾...")
        
        # 模擬從 Pinecone/Milvus/Qdrant 拿回來的原始資料 (Raw Dict)
        raw_mock_data = [
            # --- 原有的牛肉湯 (ID: 201, 202) ---
            {
                "id": 201, 
                "name": "昆山阿牛溫體牛肉湯", 
                "cuisine_type": ["台式", "在地小吃"],
                "food_type": ["牛肉湯"], 
                "flavor": ["鮮甜", "回甘"], 
                "dish_name": ["牛肉湯", "肉燥飯"],
                "review_text": "這間的湯頭真的很甜...",
                "metadata_quality": "complete"
            },
            {
                "id": 202, 
                "name": "六千牛肉湯", 
                "cuisine_type": ["台式"],
                "food_type": ["牛肉湯"], 
                "flavor": ["濃郁"], 
                "dish_name": ["牛肉湯"],
                "review_text": "要四點起來排隊的傳說級牛肉湯...",
                "metadata_quality": "partial"
            },
            
            # --- 新增：台南的火鍋店 ---
            {
                "id": 203, 
                "name": "小豪洲沙茶爐", 
                "cuisine_type": ["台式", "火鍋"],
                "food_type": ["火鍋", "沙茶爐"], 
                "flavor": ["扁魚味", "傳統"], 
                "dish_name": ["豬肉鍋", "手工魚餃"],
                "review_text": "台南必吃的沙茶火鍋，湯頭有扁魚的香味。",
                "metadata_quality": "complete"
            },
            {
                "id": 204, 
                "name": "松大沙茶爐", 
                "cuisine_type": ["台式", "火鍋"],
                "food_type": ["火鍋"], 
                "flavor": ["重口味", "沙茶"], 
                "dish_name": ["牛肉爐", "羊肉爐"],
                "review_text": "沙茶醬很厲害，肉質也不錯。",
                "metadata_quality": "complete"
            },
            {
                "id": 205, 
                "name": "詹記麻辣火鍋 (台北店)", 
                "cuisine_type": ["台式", "麻辣鍋"],
                "food_type": ["火鍋", "麻辣鍋"], 
                "flavor": ["鴨血", "麻辣"], 
                "dish_name": ["麻辣鍋", "鴨血豆腐"],
                "review_text": "台北最好吃的鴨血，一定要訂位。",
                "metadata_quality": "complete"
            }
        ]

        # 簡單的關鍵字過濾 (模擬向量搜尋的相關性)
        filtered_results = []
        for item in raw_mock_data:
            # 模擬語意搜尋：把所有欄位串起來比對
            searchable_text = str(item["food_type"]) + item["name"] + str(item["cuisine_type"]) + str(item["flavor"])
            
            if keywords in searchable_text:
                filtered_results.append(VectorSearchResult(**item))

        print(f"[Repo] Mock 搜尋完成，找到 {len(filtered_results)} 筆相關資料")
        return filtered_results

    # ==========================================
    #  未來功能：真實 Qdrant 邏輯 (封裝在內部函式)
    # ==========================================
    # def _search_qdrant_logic(self, keywords: str) -> List[VectorSearchResult]:
    #     try:
    #         # 1. 文字轉向量 (Text to Vector)
    #         # query_vector = self.model.encode(keywords).tolist()
    #
    #         # 2. 向量搜尋 (Vector Search)
    #         # search_result = self.client.search(
    #         #     collection_name=self.collection_name,
    #         #     query_vector=query_vector,
    #         #     limit=5,
    #         #     with_payload=True # 重要：回傳 Metadata
    #         # )
    #
    #         # 3. 格式轉換 (DTO Mapping)
    #         # results = []
    #         # for point in search_result:
    #         #     p = point.payload
    #         #     dto = VectorSearchResult(
    #         #         id=p.get("id"), # 或是 point.id
    #         #         name=p.get("name"),
    #         #         cuisine_type=p.get("cuisine_type"),
    #         #         food_type=p.get("food_type"),
    #         #         flavor=p.get("flavor"),
    #         #         dish_name=p.get("dish_name"),
    #         #         review_text=p.get("review_text"),
    #         #         metadata_quality=p.get("metadata_quality", "unknown")
    #         #     )
    #         #     results.append(dto)
    #         # return results
    #
    #     except Exception as e:
    #         logging.error(f"Qdrant 搜尋錯誤: {e}")
    #         return []