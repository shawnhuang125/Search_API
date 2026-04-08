import json
import re

def clean_text(text):
    """清理掉無意義的預設字串與 N/A"""
    if not text:
        return ""
    # 移除常見的無意義字串
    garbage = ["未偵測到顯著特徵", "N/A;", "N/A"]
    for g in garbage:
        text = text.replace(g, "")
    return text.strip()

def merge_summaries_per_shop(input_file, output_file):
    try:
        with open(input_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # 1. 收集每家店的所有 summary
        shop_summaries = {}

        for item in data:
            name = item.get('name')
            
            # --- 修正處：處理 level 可能為字串的情況 ---
            raw_level = item.get('level', 0)
            try:
                # 確保轉成數字再比較
                level = int(raw_level) if raw_level is not None else 0
            except (ValueError, TypeError):
                level = 0
            # ---------------------------------------

            summary = clean_text(item.get('review_summary', ''))
            
            if name not in shop_summaries:
                shop_summaries[name] = set()
            
            # 只有當 level > 1 時才併入摘要
            if level > 1 and summary:
                parts = re.split(r'[|;；\n]+', summary)
                for p in parts:
                    p_clean = p.strip()
                    if p_clean:
                        shop_summaries[name].add(p_clean)
                        
        # 2. 將收集到的 set 轉換成合併後的字串
        final_summary_map = {}
        for name, summaries in shop_summaries.items():
            if summaries:
                # 排序後合併，確保每次執行的結果順序一致
                final_summary_map[name] = " | ".join(sorted(list(summaries)))
            else:
                # 如果該店所有資料的 level 都不大於 1，或者都沒有摘要
                final_summary_map[name] = "未偵測到顯著特徵"

        # 3. 覆蓋回原始資料的每一筆 Point
        for item in data:
            name = item.get('name')
            if name in final_summary_map:
                item['review_summary'] = final_summary_map[name]

        # 4. 存檔
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        print(f"處理完成！已排除 Level 1 的摘要干擾。")
        print(f"總筆數：{len(data)}")
        print(f"店鋪總數：{len(final_summary_map)}")

    except Exception as e:
        print(f"發生錯誤: {e}")

# 執行
if __name__ == "__main__":
    merge_summaries_per_shop('restaurants_20260326.json', 'restaurants_20260326_unified.json')