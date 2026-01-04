def format_facility_tags(results):
    for row in results:
        raw_tags = row.get("facility_tags")
        
        # 這裡會判斷型別，如果是 parse_json_fields 處理過的 dict 才會進入
        if isinstance(raw_tags, dict):
            # 提取所有值為 True 的 Key 名稱
            processed_list = [k for k, v in raw_tags.items() if v is True]
            row["facility_tags"] = processed_list
        else:
            # 如果還是字串或其他型別，代表解析失敗，回傳空列表
            row["facility_tags"] = []
    return results