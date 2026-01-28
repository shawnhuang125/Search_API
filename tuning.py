from sentence_transformers import SentenceTransformer, InputExample, losses
from torch.utils.data import DataLoader
import torch
import logging
import os
from datetime import datetime
# 設定日誌格式
def init_logging(log_dir="logs"):
    """初始化日誌設定，將日誌存到指定目錄"""
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    
    # 檔名包含時間戳記，例如 logs/tuning_20260121_1430.log
    log_filename = datetime.now().strftime("tuning_%Y%m%d_%H%M%S.log")
    log_path = os.path.join(log_dir, log_filename)

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_path, encoding='utf-8'), # 存到檔案
            logging.StreamHandler() # 輸出到螢幕
        ]
    )
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

def setup_model():
    model_name = 'BAAI/bge-m3'
    logging.info(f"正在載入 BGE-M3 模型 ({model_name})...")
    
    # 載入模型
    model = SentenceTransformer(model_name)
    
    # 檢查並移動至 GPU
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model.to(device)
    
    logging.info(f"--- 模型載入完成 ---")
    logging.info(f"目前執行設備: {device}")
    if device == "cuda":
        logging.info(f"顯卡型號: {torch.cuda.get_device_name(0)}")
    
    return model


def start_finetuning(model):
    """
    微調邏輯：等 Dataset 準備好後再呼叫此函數
    """
    logging.info("準備微調資料集...")
    
    # 這裡放你的專題資料（目前為範例）
    train_examples = [
        InputExample(texts=['高雄左營哪裡有推薦的素食？', '這家位於左營的蔬食餐廳提供精緻的排餐與有機沙拉...']),
        InputExample(texts=['我想找好吃的噴水雞肉飯', '這間嘉義雞肉飯名店的特色是雞油香氣濃郁，肉質鮮嫩多汁...']),
    ]

    # 4060 8GB 顯存建議 batch_size 設為 4-8
    train_dataloader = DataLoader(train_examples, shuffle=True, batch_size=4)
    train_loss = losses.MultipleNegativesRankingLoss(model=model)

    logging.info("開始執行微調 (Epochs: 3)...")
    model.fit(
        train_objectives=[(train_dataloader, train_loss)],
        epochs=3,
        warmup_steps=10,
        output_path='./m3_food_finetuned'
    )
    logging.info("微調完成！模型已儲存至 ./m3_food_finetuned")

if __name__ == "__main__":
    # 初始化logging
    init_logging("logs")
    # 確認GPU是否正常運行
    check_gpu()
    # 正式初始化模型
    # 這一步會觸發模型下載，如果是第一次執行會需要一點時間
    bge_model = setup_model()
    
    # 簡單測試模型推論 (確保 1024 維向量能正常產出)
    if bge_model:
        test_text = "高雄左營蔬食餐廳"
        embedding = bge_model.encode(test_text)
        logging.info(f"測試推論成功！向量維度為: {len(embedding)}")
        # 預期輸出應該是 1024