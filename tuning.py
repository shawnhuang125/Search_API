from sentence_transformers import SentenceTransformer, InputExample, losses, util
from torch.utils.data import DataLoader
import torch
import logging
import os
from datetime import datetime
import json
# 設定日誌格式
def init_logging(log_dir="logs"):
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    
    log_filename = datetime.now().strftime("tuning_%Y%m%d_%H%M%S.log")
    log_path = os.path.join(log_dir, log_filename)

    # 設置基礎日誌格式
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    
    file_handler = logging.FileHandler(log_path, encoding='utf-8')
    file_handler.setFormatter(formatter)
    
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)

    # 獲取 root logger 並設置
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(stream_handler)
    
    # 【關鍵】強制捕獲 SentenceTransformer 的訓練日誌
    st_logger = logging.getLogger('sentence_transformers')
    st_logger.setLevel(logging.INFO)
    st_logger.propagate = True # 確保訊息會傳遞到 root logger 的 handler
    
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

def test_model_search(model_path='./m3_food_finetuned', json_path='formatted_data_20260129.json'):
    if not os.path.exists(model_path):
        print(f"❌ 找不到模型資料夾：{model_path}")
        return

    print(f"正在載入模型：{model_path}...")
    model = SentenceTransformer(model_path)
    with open(json_path, 'r', encoding='utf-8') as f:
        raw_data = json.load(f)

    # --- [修正 1] 資料去重：根據店名排除重複項，同時確保 original_id 存在 ---
    data = []
    seen_names = set()
    for item in raw_data:
        name = item.get('name', '').strip()
        if name and name not in seen_names:
            data.append(item)
            seen_names.add(name)
    print(f"原始資料 {len(raw_data)} 筆，去重後剩餘 {len(data)} 筆")

    embedding_cache_path = "corpus_embeddings.pt"
    
    # --- [修正 2] 強化特徵組合：建立檢索用的文本索引 ---
    corpus = []
    for item in data:
        name = item.get('name', '未知')
        def get_tags(key):
            return [str(t) for t in item.get(key, []) if str(t).lower() != 'nan' and t]
            
        c_types = get_tags('cuisine_type')
        f_types = get_tags('food_type')
        flavors = get_tags('flavor')
        s_tags = get_tags('service_tags')
        
        # 構造檢索文本：明確標註欄位能幫助 BGE-M3 更精準對齊
        text = f"店名：{name} | 料理：{' '.join(c_types)} | 品項：{' '.join(f_types)} | 口感：{' '.join(flavors)} | 特色：{' '.join(s_tags)}"
        corpus.append(text)

    # 如果有舊的資料庫轉向量的檔案就沿用舊的~不要在每次轉向量
    if os.path.exists(embedding_cache_path):
        print("⚡ 偵測到向量快取，正在載入索引以加速啟動...")
        corpus_embeddings = torch.load(embedding_cache_path)
    else:
        print("🔍 找不到快取，正在將資料轉化為向量 (僅需一次)...")
        # 建立 corpus 文本
        corpus = []
        for item in data:
            name = item.get('name', '未知')
            def get_tags(key):
                return [str(t) for t in item.get(key, []) if str(t).lower() != 'nan' and t]
            c_types, f_types, flavors, s_tags = get_tags('cuisine_type'), get_tags('food_type'), get_tags('flavor'), get_tags('service_tags')
            text = f"店名：{name} | 菜系：{' '.join(c_types)} | 食物種類：{' '.join(f_types)} | 口味：{' '.join(flavors)} | 服務標籤：{' '.join(s_tags)}"
            corpus.append(text)

        corpus_embeddings = model.encode(corpus, convert_to_tensor=True)
        torch.save(corpus_embeddings, embedding_cache_path)
        print(f"✅ 向量快取已存至 {embedding_cache_path}")

    while True:
        user_query = input("\n🔎 請輸入要測試的特徵 (如: 日式、甜點、冷氣涼): ").strip()
        if user_query.lower() == 'exit': break
        if not user_query: continue
        
        # 搜尋時也稍微修飾 query 以符合訓練時的對話語感
        query_emb = model.encode(f"想吃{user_query}", convert_to_tensor=True)
        hits = util.semantic_search(query_emb, corpus_embeddings, top_k=5)[0]

        print(f"\n--- 搜尋「{user_query}」的前 5 名結果 ---")
        print("=" * 60)
        for i, hit in enumerate(hits, 1):
            idx = hit['corpus_id']
            score = hit['score']
            item = data[idx]
            
            # 提取你的 payload 欄位 original_id
            oid = item.get('original_id', 'N/A')
            
            print(f"排名 {i} | 相似度分數: {score:.2%}")
            print(f"【ID】: {oid}")
            print(f"【店名】: {item['name']}")
            print(f"【標籤維度】:")
            print(f"  - 菜系: {'/'.join(item.get('cuisine_type', []))}")
            print(f"  - 食物種類: {'/'.join(item.get('food_type', []))}")
            print(f"  - 口味: {'/'.join(item.get('flavor', []))}")
            print(f"  - 服務標籤: {'/'.join(item.get('service_tags', []))}")
            print(f"【摘要】: {item.get('review_summary', '')[:60]}...")
            print("-" * 60)

import argparse

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", type=str, choices=["train", "search"], default="search")
    args = parser.parse_args()

    init_logging("logs")
    json_file = "formatted_dara_20260203.json"
    output_path = os.path.abspath("./m3_food_finetuned")

    if args.mode == "train":
        check_gpu()

        # 嘗試取得舊路徑
        old_model_path = "./m3_food_finetuned"

        # 建立模型並自動識別模式
        bge_model, is_incremental = setup_model(old_model_path)

        # 開始訓練 (傳入識別標籤)
        if os.path.exists(json_file):
            start_finetuning(bge_model, is_incremental, json_path=json_file)
            # 訓練完自動刪除舊快取，確保下次搜尋會重新產出新模型的向量
            if os.path.exists("corpus_embeddings.pt"):
                os.remove("corpus_embeddings.pt")
                
    elif args.mode == "search":
        # 呼叫修正後的測試函數
        test_model_search(model_path=output_path, json_path=json_file)