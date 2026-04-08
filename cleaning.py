import json
import os
import ollama
from tqdm import tqdm

def extract_summary_locally(review_text, model_name='qwen2.5:7b'):
    """
    呼叫本地 Ollama 模型進行資訊提取。
    model_name: 可以換成 'qwen2.5:1.5b' 以獲得更快的速度。
    """
    if not review_text or len(review_text) < 5:
        return "評論內容過短，無法提取特徵。"

    # 設定精確的 Prompt，要求它只提取原文片段
    prompt = f"""
    你是一位美食數據清洗專家。請閱讀下方的『原始評論』，並從中提取出：
    1. 食物口感描述（例如：肉質肥、燉得很爛、番茄味香、不油、濕潤）。
    2. 軟服務標籤片段（例如：積極回應、出餐速度快、老闆友善、沒介紹）。

    規則：
    - 直接輸出提取到的原文字句。
    - 使用分號『；』隔開不同片段。
    - 不要解釋，不要回覆摘要以外的任何文字。
    - 若完全沒提到，請回傳「無顯著特徵」。

    原始評論："{review_text}"
    提取結果："""
    
    try:
        response = ollama.generate(model=model_name, prompt=prompt)
        # 取得模型輸出的內容並去背空白
        result = response['response'].strip()
        return result
    except Exception as e:
        print(f"提取出錯: {e}")
        return "提取失敗"

def run_stage_one_cleaning(input_file, output_file):
    """階段一：讀取 JSON 並利用本地 LLM 覆蓋 review_summary"""
    
    if not os.path.exists(input_file):
        print(f"找不到檔案: {input_file}")
        return

    with open(input_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    print(f"開始執行階段一：本地 LLM 語義提取 (使用 Qwen2.5)...")
    
    # 遍歷資料進行清洗
    for item in tqdm(data):
        review_text = item.get("review_text", "")
        
        # 執行提取並直接覆蓋原本的 review_summary
        extracted_info = extract_summary_locally(review_text)
        item["review_summary"] = extracted_info

    # 儲存清洗後的結果
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"\n階段一完成！清洗後的資料已存至: {output_file}")
    print("提示：現在您可以關閉 Ollama 以釋放顯存，準備進行階段二的 M3 向量化。")

# 執行範例
if __name__ == "__main__":
    # 確保你已經在終端機跑過 ollama pull qwen2.5:7b
    run_stage_one_cleaning("restaurants_20260322_1432.json", "data_stage1_cleaned.json")