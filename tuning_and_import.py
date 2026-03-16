from sentence_transformers import SentenceTransformer, InputExample, losses, util
from torch.utils.data import DataLoader
import torch
import logging
import os
from datetime import datetime
import json
from qdrant_client import QdrantClient
from qdrant_client.http import models as rest

# 設定日誌格式
def init_logging(log_dir="logs"):
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    
    log_filename = datetime.now().strftime("tuning_%Y%m%d_%H%M%S.log")
    log_path = os.path.join(log_dir, log_filename)

    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    
    file_handler = logging.FileHandler(log_path, encoding='utf-8')
    file_handler.setFormatter(formatter)
    
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(stream_handler)
    
    st_logger = logging.getLogger('sentence_transformers')
    st_logger.setLevel(logging.INFO)
    st_logger.propagate = True 
    
    logging.info(f"日誌系統初始化完成，存檔路徑: {log_path}")


def check_gpu():
    print(f"PyTorch 版本: {torch.__version__}")
    print(f"CUDA 是否可用: {torch.cuda.is_available()}")
    
    if torch.cuda.is_available():
        print(f"顯卡型號: {torch.cuda.get_device_name(0)}")
        print(f"CUDA 版本: {torch.version.cuda}")
        # 測試分配顯存
        x = torch.randn(1024, 1024).cuda()
        print("測試成功：已成功在 GPU 上建立 1024x1024 張量！")
    else:
        print("依然找不到 GPU。請確認 NVIDIA 驅動程式已安裝，並重新啟動 IDE。")

def load_json_data(file_path):
    if not os.path.exists(file_path):
        logging.error(f"找不到檔案: {file_path}")
        return []

    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    examples = []
    for item in data:
        # --- 1. 嚴格提取四大維度，並過濾掉 nan 或空值 ---
        def clean_tags(tags):
            if not isinstance(tags, list): return []
            return [str(t) for t in tags if str(t).lower() != 'nan' and t]

        name = str(item.get('name', '未知餐廳'))
        c_types = clean_tags(item.get('cuisine_type', [])) # 料理類型 (義式, 台式)
        f_types = clean_tags(item.get('food_type', []))    # 食物種類 (甜點, 麵食)
        flavors = clean_tags(item.get('flavor', []))       # 口感味道 (酸, 甜, 辣)
        s_tags = clean_tags(item.get('service_tags', []))  # 服務特色 (環境, 涼)
        summary = item.get('review_summary', '')

        if name == 'nan' or not any([c_types, f_types, flavors]):
            continue # 跳過資料不齊全的無意義樣本

        # --- 2. 構造「邏輯樹特徵塊」作為 Passage ---
        # 這是 RAG 檢索的核心，我們把所有關鍵特徵揉在一起
        passage = (
            f"店名：{name} | "
            f"類別：{'/'.join(c_types)} | "
            f"品項：{'/'.join(f_types)} | "
            f"口味：{'/'.join(flavors)} | "
            f"特色：{'/'.join(s_tags)} | "
            f"摘要：{summary}"
        )

        # --- 3. 多重訓練策略 (對應你的邏輯樹分支) ---
        # 策略 A: 品項搜尋 (解決你之前「甜點」搜不到的問題)
        if f_types:
            for ft in f_types:
                examples.append(InputExample(texts=[f"我想吃{ft}", passage]))

        # 策略 B: 口味 + 品項 組合搜尋
        if f_types and flavors:
            examples.append(InputExample(texts=[f"{flavors[0]}的{f_types[0]}", passage]))

        # 策略 C: 料理類型 + 特色 (適合服務類的問句)
        if c_types and s_tags:
            examples.append(InputExample(texts=[f"{c_types[0]}且{s_tags[0]}", passage]))

        # 策略 D: 純店名 (基本保障)
        examples.append(InputExample(texts=[name, passage]))
            
    logging.info(f"成功處理 {len(data)} 筆資料，生成 {len(examples)} 組邏輯樹訓練對")
    return examples

from sentence_transformers import SentenceTransformer, InputExample, losses, util
from torch.utils.data import DataLoader
import torch
import logging
import os
from datetime import datetime
import json
import uuid  # 新增：用於產生唯一的 Qdrant Point ID
from qdrant_client import QdrantClient
from qdrant_client.http import models as rest
from qdrant_client.models import PointStruct, VectorParams, Distance # 新增：用於建立 Collection 與 Point

# ==========================================
# 1. 系統與日誌初始化
# ==========================================
def init_logging(log_dir="logs"):
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    
    log_filename = datetime.now().strftime("tuning_%Y%m%d_%H%M%S.log")
    log_path = os.path.join(log_dir, log_filename)

    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    
    file_handler = logging.FileHandler(log_path, encoding='utf-8')
    file_handler.setFormatter(formatter)
    
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(stream_handler)
    
    st_logger = logging.getLogger('sentence_transformers')
    st_logger.setLevel(logging.INFO)
    st_logger.propagate = True 
    
    logging.info(f"日誌系統初始化完成，存檔路徑: {log_path}")

def check_gpu():
    print(f"PyTorch 版本: {torch.__version__}")
    print(f"CUDA 是否可用: {torch.cuda.is_available()}")
    
    if torch.cuda.is_available():
        print(f"顯卡型號: {torch.cuda.get_device_name(0)}")
        print(f"CUDA 版本: {torch.version.cuda}")
    else:
        print("依然找不到 GPU。請確認 NVIDIA 驅動程式已安裝，並重新啟動 IDE。")

def setup_model(model_path=None):
    if model_path and os.path.exists(model_path):
        target = model_path
        logging.info(f"🔄 偵測到現有模型路徑，載入本地模型：{target}")
        is_incremental = True
    else:
        target = 'BAAI/bge-m3'
        logging.info(f"🆕 未發現舊模型，載入原始預訓練模型：{target}")
        is_incremental = False
    
    model = SentenceTransformer(target)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model.to(device)
    
    logging.info(f"--- 模型載入完成 ({target}) ---")
    return model, is_incremental 

# ==========================================
# 2. 訓練專用 Functions (原有的邏輯)
# ==========================================
def load_json_data(file_path):
    if not os.path.exists(file_path):
        logging.error(f"找不到檔案: {file_path}")
        return []

    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    examples = []
    for item in data:
        def clean_tags(tags):
            if not isinstance(tags, list): return []
            return [str(t) for t in tags if str(t).lower() != 'nan' and t]

        name = str(item.get('name', '未知餐廳'))
        c_types = clean_tags(item.get('cuisine_type', [])) 
        f_types = clean_tags(item.get('food_type', []))    
        flavors = clean_tags(item.get('flavor', []))       
        s_tags = clean_tags(item.get('service_tags', []))  
        summary = item.get('review_summary', '')

        if name == 'nan' or not any([c_types, f_types, flavors]):
            continue 

        passage = (
            f"店名：{name} | "
            f"類別：{'/'.join(c_types)} | "
            f"品項：{'/'.join(f_types)} | "
            f"口味：{'/'.join(flavors)} | "
            f"特色：{'/'.join(s_tags)} | "
            f"摘要：{summary}"
        )

        if f_types:
            for ft in f_types:
                examples.append(InputExample(texts=[f"我想吃{ft}", passage]))
        if f_types and flavors:
            examples.append(InputExample(texts=[f"{flavors[0]}的{f_types[0]}", passage]))
        if c_types and s_tags:
            examples.append(InputExample(texts=[f"{c_types[0]}且{s_tags[0]}", passage]))
        examples.append(InputExample(texts=[name, passage]))
            
    logging.info(f"成功處理 {len(data)} 筆資料，生成 {len(examples)} 組邏輯樹訓練對")
    return examples

def setup_model(model_path=None):
    # 邏輯：判斷要載入本地微調過的，還是原始的 BGE-M3
    if model_path and os.path.exists(model_path):
        target = model_path
        logging.info(f"🔄 偵測到現有模型路徑，準備進行【增量微調】模式：{target}")
        is_incremental = True
    else:
        target = 'BAAI/bge-m3'
        logging.info(f"🆕 未發現舊模型，準備進行【全新訓練】模式：{target}")
        is_incremental = False
    
    # 注意這裡要傳入 target 而不是固定的 'BAAI/bge-m3'
    model = SentenceTransformer(target)
    
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model.to(device)
    
    logging.info(f"--- 模型載入完成 ({target}) ---")
    return model, is_incremental # 確保回傳兩個值

def start_finetuning(model, is_incremental, json_path="data.json"):
    logging.info(f"🚀 啟動訓練流程，目標資料：{json_path}")
    
    model.max_seq_length = 512 
    train_examples = load_json_data(json_path)
    
    if not train_examples:
        logging.warning("❌ 沒有可用的訓練資料。")
        return

    # --- 關鍵邏輯：根據模式設定權重凍結與參數 ---
    if is_incremental:
        # 【增量微調模式】
        # 鎖定底層，預防災難性遺忘與舊資料過度聚合
        auto_model = model[0].auto_model
        freeze_until = int(len(auto_model.encoder.layer) * 0.7) 
        for param in auto_model.embeddings.parameters():
            param.requires_grad = False
        for layer in auto_model.encoder.layer[:freeze_until]:
            for param in layer.parameters():
                param.requires_grad = False
        
        learning_rate = 1e-6  # 極低學習率
        epochs = 1            # 少量次數
        logging.info(f"🛡️ 已鎖定底層權重，採用增量參數：LR={learning_rate}, Epochs={epochs}")
    else:
        # 【全新訓練模式】
        # 開放所有權重，讓模型完整學習你的資料佈局
        learning_rate = 2e-5  # 標準微調學習率
        epochs = 3            # 較多次數
        logging.info(f"🔥 開放全權重訓練，採用標準參數：LR={learning_rate}, Epochs={epochs}")

    # --- 通用訓練配置 ---
    batch_size = 4
    total_steps = (len(train_examples) // batch_size) * epochs
    warmup_steps = int(total_steps * 0.1)
    
    train_dataloader = DataLoader(train_examples, shuffle=True, batch_size=batch_size)
    train_loss = losses.MultipleNegativesRankingLoss(model=model)

    try:
        model.fit(
            train_objectives=[(train_dataloader, train_loss)],
            epochs=epochs,
            warmup_steps=warmup_steps,
            output_path='./m3_food_finetuned',
            show_progress_bar=True,
            use_amp=True,
            optimizer_params={'lr': learning_rate},
            checkpoint_path='./m3_checkpoints',
            checkpoint_save_steps=200
        )
        logging.info(f"✅ 訓練完成！模型已儲存至 ./m3_food_finetuned")
    except Exception as e:
        logging.error(f"❌ 訓練中斷: {str(e)}", exc_info=True)



# 匯入 Qdrant 專用 Functions
def prepare_data_for_import(file_path):
    """讀取 JSON 並將每筆資料轉換為可供 Embedding 的自然語言描述"""
    if not os.path.exists(file_path):
        logging.error(f"找不到檔案: {file_path}")
        return []

    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    processed_data = []
    for item in data:
        def clean_tags(tags):
            if not isinstance(tags, list): return []
            return [str(t) for t in tags if str(t).lower() != 'nan' and t]

        name = str(item.get('name', '未知餐廳'))
        c_types = clean_tags(item.get('cuisine_type', []))
        f_types = clean_tags(item.get('food_type', []))
        flavors = clean_tags(item.get('flavor', []))
        s_tags = clean_tags(item.get('service_tags', []))
        summary = item.get('review_summary', '')
        review_text = item.get('review_text', '') # 特別加入評論原文，豐富搜尋特徵

        if name == 'nan' or not any([c_types, f_types, flavors]):
            continue

        # 組合給模型看的自然語言描述
        passage = (
            f"這家店的店名是{name} | "
            f"主打的菜系是{'/'.join(c_types)} | "
            f"主打的食物種類是{'/'.join(f_types)} | "
            f"主打的口味有{'/'.join(flavors)} | "
            f"評論資料中提到的服務標籤有{'/'.join(s_tags)} | "
            f"評論資料的摘要是{summary} | "
            f"原始評論內容為{review_text}"
        )

        processed_data.append({
            "id": str(uuid.uuid4()), # Qdrant 需要唯一 UUID
            "text_to_embed": passage,
            "payload": item # 整個 JSON 當作 Payload
        })

    logging.info(f"資料準備完成，共 {len(processed_data)} 筆有效 Point 即將匯入。")
    return processed_data

# 建立並初始化向量資料庫
def init_qdrant_collection(client, collection_name, vector_size=1024):
    """檢查並初始化 Qdrant Collection"""
    try:
        client.get_collection(collection_name)
        logging.info(f"✅ Qdrant Collection '{collection_name}' 已存在。")
    except Exception:
        logging.info(f"⚠️ Collection '{collection_name}' 不存在，正在自動建立...")
        client.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
        )
        logging.info(f"✅ 成功建立 Collection: '{collection_name}' (維度: {vector_size})")

def start_import_qdrant(model, json_path, collection_name, qdrant_host="192.168.1.112", batch_size=64):
    """執行批次向量化與匯入流程"""
    logging.info(f"🚀 啟動匯入流程，目標資料庫: {qdrant_host}:{6333}")
    client = QdrantClient(host=qdrant_host, port=6333)

    # 1. 初始化資料庫 (BGE-M3 的預設輸出維度是 1024)
    init_qdrant_collection(client, collection_name, vector_size=1024)

    # 2. 準備文本與 Payload
    import_data = prepare_data_for_import(json_path)
    if not import_data:
        return

    total_points = len(import_data)
    logging.info(f"開始批次向量化與匯入，Batch Size 設定為: {batch_size}")

    # 3. 分批處理 (Batching) 避免 OOM 與網路超時
    for i in range(0, total_points, batch_size):
        batch = import_data[i : i + batch_size]

        # 提取文字，一次丟給 GPU 進行平行運算
        texts = [item["text_to_embed"] for item in batch]
        vectors = model.encode(texts).tolist()

        # 組裝 PointStruct
        points = []
        for j, item in enumerate(batch):
            points.append(
                PointStruct(
                    id=item["id"],
                    vector=vectors[j],
                    payload=item["payload"]
                )
            )

        # 批次寫入 Qdrant
        client.upsert(
            collection_name=collection_name,
            points=points
        )
        logging.info(f"📈 匯入進度: {min(i + batch_size, total_points)} / {total_points}")

    logging.info("🎉 恭喜！全數資料向量化並匯入 Qdrant 完成！")


def test_model_search_qdrant(model_path='./m3_food_finetuned', collection_name="restaurants",qdrant_host="192.168.1.112", qdrant_port=6333):
    # 1. 初始化模型
    if not os.path.exists(model_path):
        print(f"❌ 找不到模型資料夾：{model_path}")
        return
    print(f"正在載入微調模型：{model_path}...")
    model = SentenceTransformer(model_path)

    # 2. 初始化 Qdrant 客戶端 (假設你跑在本地，或是填入你的雲端 URL/API Key)
    client = QdrantClient(host=qdrant_host, port=6333) 
    
    # 檢查 Collection 是否存在
    try:
        client.get_collection(collection_name)
        print(f"✅ 已連接至 Qdrant Collection: {collection_name}")
    except Exception:
        # --- 加入這段調試代碼 ---
        collections = client.get_collections().collections
        existing_names = [c.name for c in collections]
        print(f"❌ 找不到 Collection: '{collection_name}'")
        print(f"目前資料庫中存在的 Collection 有: {existing_names}")
        return

    while True:
        user_query = input("\n🔎 請輸入要測試的特徵 (如: 日式、甜點): ").strip()
        if user_query.lower() == 'exit': break
        if not user_query: continue
        
        # 3. 將 User Query 轉為向量 (維持訓練時的語感)
        query_vector = model.encode(f"想吃{user_query}").tolist()

        # 4. 向 Qdrant 發動搜尋
        search_result = client.query_points(
            collection_name=collection_name,
            query=query_vector,       # 直接傳入向量
            limit=5,
            with_payload=True
        ).points  # 注意：query_points 回傳的是一個物件，結果在 .points 裡面

        print(f"\n--- Qdrant 搜尋「{user_query}」的前 5 名結果 ---")
        print("=" * 60)
        for i, hit in enumerate(search_result, 1):
            payload = hit.payload
            score = hit.score
            
            print(f"排名 {i} | 相似度分數: {score:.2%}")
            print(f"【ID】: {payload.get('original_id', 'N/A')}")
            print(f"【店名】: {payload.get('name', '未知')}")
            print(f"【標籤維度】:")
            print(f"  - 菜系: {payload.get('cuisine_type', [])}")
            print(f"  - 食物種類: {payload.get('food_type', [])}")
            print(f"【摘要】: {payload.get('review_summary', '')[:60]}...")
            print("-" * 60)

import argparse

if __name__ == "__main__":
    """
    使用方法說明 (Usage Guide):
    
    1. 訓練模式 (Train): 針對在地美食語境進行微調
       指令: python tuning.py --mode train
       
    2. 匯入模式 (Import): 將 JSON 資料轉為向量並推送到 Qdrant
       指令: python tuning.py --mode import --collection restaurants
       
    3. 搜尋模式 (Search): 測試向量資料庫的檢索效果
       指令: python tuning.py --mode search --collection restaurants
    """

    parser = argparse.ArgumentParser(description="AI美食推薦系統 - 向量模型訓練與資料庫管理工具")
    
    # 模式選擇: 
    # train: 執行 MultipleNegativesRankingLoss 微調
    # import: 執行預處理、向量化並存入 Qdrant
    # search: 進入互動式命令列測試搜尋品質
    parser.add_argument("--mode", type=str, choices=["train", "search", "import"], default="search", help="執行模式")
    
    # Collection 名稱: 指定 Qdrant 中的資料集名稱
    parser.add_argument("--collection", type=str, default="restaurants", help="Qdrant Collection 名稱")
    
    args = parser.parse_args()

    # 初始化日誌系統: 記錄訓練與匯入過程，方便除錯
    init_logging("logs")
    
    # 設定資料路徑 (請確保此檔案存在於腳本同級目錄)
    json_file = "formatted_dara_20260203.json" 
    
    # 設定模型儲存/載入路徑
    output_path = os.path.abspath("./m3_food_finetuned")

    # 1. 環境檢查: 確認是否有可用的 NVIDIA GPU
    check_gpu()

    # 2. 載入模型: 優先載入 './m3_food_finetuned'，若無則下載原始 BAAI/bge-m3
    bge_model, is_incremental = setup_model(output_path)

    # --- 執行邏輯分支 ---

    if args.mode == "train":
        # 訓練流程: 將文字對轉化為向量空間的鄰近關係
        if os.path.exists(json_file):
            start_finetuning(bge_model, is_incremental, json_path=json_file)
            # 清理訓練產生的快取檔案
            if os.path.exists("corpus_embeddings.pt"):
                os.remove("corpus_embeddings.pt")
        else:
            print(f"❌ 錯誤: 找不到訓練所需的 JSON 檔案: {json_file}")
                
    elif args.mode == "import":
        # 匯入流程: 執行 [自然語言合成] -> [批次向量化] -> [Qdrant Upsert]
        if os.path.exists(json_file):
            start_import_qdrant(
                model=bge_model, 
                json_path=json_file, 
                collection_name=args.collection,
                qdrant_host="192.168.1.112", # Qdrant Server IP
                batch_size=64                # 4060Ti 16GB 建議設定 64-128
            )
        else:
            print(f"❌ 錯誤: 找不到欲匯入的 JSON 檔案: {json_file}")

    elif args.mode == "search":
        # 搜尋測試: 模擬前端請求，輸入中文查詢語句進行語義匹配
        test_model_search_qdrant(
            model_path=output_path, 
            collection_name=args.collection,
            qdrant_host="192.168.1.112"
        )    