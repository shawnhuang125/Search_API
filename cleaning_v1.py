import json
import os
import ollama
import re
from tqdm import tqdm
from opencc import OpenCC

cc = OpenCC('s2twp')

def get_llm_response(prompt, model_name='qwen2.5:7b'):
    try:
        response = ollama.generate(
            model=model_name, 
            prompt=prompt,
            options={"temperature": 0.1, "top_p": 0.1, "num_predict": 100} # 稍微提高溫控增加彈性
        )
        result = cc.convert(response['response'].strip())
        
        # --- 修正點 1：不再這裡直接殺掉整個 result ---
        # 讓內容流向 clean_and_merge 去處理具體片段
        if result.upper() == "N/A":
            return ""
        return result
    except Exception as e:
        print(f"\nLLM 執行失敗: {e}")
        return ""

def clean_and_merge(extracted_list):
    pieces = []
    for item in extracted_list:
        if not item: continue
        # 拆分常見分隔符
        split_items = re.split(r'[;；,，\n]', item)
        for p in split_items:
            p = p.strip()
            # --- 修正點 2：在片段層級過濾雜質 ---
            # 排除掉包含 "沒提到"、"N/A" 的無效片段，保留有意義的內容
            is_noise = re.search(r'N/A|無相關|未提到|無提取|沒提到|內容中未|無法提取', p, re.IGNORECASE)
            if p and not is_noise and len(p) > 1:
                pieces.append(p)
    return list(dict.fromkeys(pieces))

def run_triple_stage_pipeline(input_file, output_file):
    if not os.path.exists(input_file): return

    with open(input_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    print(f"🚀 啟動優化後的標籤工程 (不再誤殺標籤)...")
    
    for item in tqdm(data, desc="精確標籤化"):
        review_text = item.get("review_text", "")
        if not review_text or len(review_text) < 2:
            item["review_summary"], item["review_labeling_level"] = "無評論內容", 1
            continue

        # --- 任務定義 ---
        tasks = {
            "food": "食物口味、口感、食材內容",
            "service": "服務態度、專業度",
            "env": "環境衛生、氣氛",
            "speed": "出餐速度、排隊",
            "other": "價格、停車、設施"
        }
        
        extracted_results = []
        for key, desc in tasks.items():
            # 修正 Prompt，告訴模型不要廢話
            prompt = f"[任務] 提取「{desc}」。\n[規則] 1.直接輸出原文短句 2.多個以分號隔開 3.若無則僅回傳 N/A。\n[評論] \"{review_text}\"\n[輸出]"
            res = get_llm_response(prompt)
            if res: extracted_results.append(res)

        final_tags = clean_and_merge(extracted_results)
        item["review_summary"] = "；".join(final_tags) if final_tags else ""

        # --- 修正點 3：改進負面情緒攔截邏輯 ---
        sentiment_prompt = f"判斷此評論是否包含「不滿、抱怨、缺點或負面情緒」？是請回 YES，完全正面或中性回 NO。評論:\"{review_text}\""
        is_negative = get_llm_response(sentiment_prompt).upper()

        # --- 修正點 4：調整 Level 判定，兼顧負評與資訊價值 ---
        tag_count = len(final_tags)
        
        if "YES" in is_negative:
            # 如果是負面，但描述非常具體 (標籤多)，提升到 Level 2 作為具體改進參考
            # 若描述很少則維持 Level 1
            level = 2 if tag_count >= 3 else 1
        else:
            # 正面評論的判定
            if tag_count >= 3:
                level = 3
            elif tag_count >= 1:
                level = 2
            else:
                level = 1

        item["review_labeling_level"] = level

    # 排序與存檔
    data.sort(key=lambda x: int(x.get("place_id", 999999)))
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    run_triple_stage_pipeline("restaurants_0326_20260329_2006.json", "restaurants_0326_20260329_2006_summary_labeled.json")