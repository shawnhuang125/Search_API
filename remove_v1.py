import json

def filter_level_one(input_file, output_file):
    try:
        # 1. 讀取原始 JSON 檔案
        with open(input_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # 2. 過濾資料：只保留 level 不等於 1 的項目
        # 這裡使用列表推導式 (List Comprehension)
        filtered_data = [item for item in data if item.get('level') != 1]
        
        # 3. 將處理後的結果寫入新檔案
        with open(output_file, 'w', encoding='utf-8') as f:
            # indent=2 讓輸出的 JSON 格式漂亮易讀，ensure_ascii=False 確保中文不變亂碼
            json.dump(filtered_data, f, indent=2, ensure_ascii=False)
            
        print(f"處理完成！已移除 level: 1 的項目。")
        print(f"原始項目數量: {len(data)}")
        print(f"剩餘項目數量: {len(filtered_data)}")
        print(f"結果已儲存至: {output_file}")

    except FileNotFoundError:
        print("錯誤：找不到指定的輸入檔案。")
    except json.JSONDecodeError:
        print("錯誤：JSON 格式不正確，無法解析。")
    except Exception as e:
        print(f"發生未知錯誤: {e}")

# --- 執行部分 ---
# 請確保 'data.json' 檔案存在於你的資料夾中
input_filename = 'summary_labeled_restaurants_20260324.json' 
output_filename = 'restaurants_20260324_cleaned_v1.json'

filter_level_one(input_filename, output_filename)