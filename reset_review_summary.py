import json
import tkinter as tk
from tkinter import filedialog, messagebox

def process_json():
    # 建立隱藏的 Tkinter 主視窗
    root = tk.Tk()
    root.withdraw()

    # 1. 讓使用者選擇 JSON 檔案
    file_path = filedialog.askopenfilename(
        title="請選擇 JSON 檔案",
        filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
    )

    if not file_path:
        print("未選擇任何檔案，程式結束。")
        return

    try:
        # 2. 讀取 JSON 檔案
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # 3. 檢查資料格式並重製 review_summary
        if isinstance(data, list):
            for item in data:
                if "review_summary" in item:
                    item["review_summary"] = ""
            
            # 4. 寫回檔案 (這裡預設覆蓋原檔，若要另存新檔可修改 file_path)
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            
            messagebox.showinfo("成功", f"處理完成！\n檔案已更新：{file_path}")
            print(f"成功更新檔案: {file_path}")
        else:
            messagebox.showerror("錯誤", "JSON 格式不符合預期（應為列表格式）")

    except Exception as e:
        messagebox.showerror("錯誤", f"發生錯誤: {str(e)}")
        print(f"發生錯誤: {e}")

if __name__ == "__main__":
    process_json()