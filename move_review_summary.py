import json
import logging

# 設定日誌
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

def update_review_summary(old_json_path, new_json_path, output_json_path):
    """
    從舊 JSON 讀取 review_summary，並根據 ID 對應更新到新 JSON 中。
    """
    try:
        # 1. 讀取舊的 JSON 檔案
        with open(old_json_path, 'r', encoding='utf-8') as f:
            old_data = json.load(f)
        
        # 2. 建立一個對照表 (Mapping): { "id": "summary" }
        # 這裡會處理 original_id 為字串或數字的情況，統一轉為 int
        summary_map = {}
        for item in old_data:
            oid = item.get("original_id")
            summary = item.get("review_summary")
            if oid is not None:
                summary_map[int(oid)] = summary

        # 3. 讀取新的 JSON 檔案 (目標檔案)
        with open(new_json_path, 'r', encoding='utf-8') as f:
            new_data = json.load(f)

        # 4. 開始更新
        update_count = 0
        for item in new_data:
            pid = item.get("place_id")
            if pid is not None and int(pid) in summary_map:
                # 將舊檔案的 summary 寫入新檔案
                item["review_summary"] = summary_map[int(pid)]
                update_count += 1
        
        # 5. 輸出結果
        with open(output_json_path, 'w', encoding='utf-8') as f:
            json.dump(new_data, f, ensure_ascii=False, indent=2)
            
        logging.info(f"更新完成！共比對並更新了 {update_count} 筆 review_summary。")
        logging.info(f"輸出檔案：{output_json_path}")

    except Exception as e:
        logging.error(f"處理過程中發生錯誤: {e}")

if __name__ == "__main__":
    # 請修改為你實際的檔案名稱
    OLD_FILE = "restaurants_20260326_unified.json"           # 含有 original_id 的舊檔
    NEW_FILE = "restaurants_20260326_all.json"  # 含有 place_id 的目標新檔
    OUTPUT_FILE = "restaurants_20260326_all_fixed.json" # 輸出結果
    
    update_review_summary(OLD_FILE, NEW_FILE, OUTPUT_FILE)