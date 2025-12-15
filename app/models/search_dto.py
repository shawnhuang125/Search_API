
# app/models/search_dto.py
from dataclasses import dataclass, field
from typing import List, Optional

@dataclass
class VectorSearchResult:
    """
    這是搜尋結果的標準資料格式 (DTO)。
    Service 層只會看到這個物件，不會看到原始的 Dictionary。
    """
    id: int
    name: str
    cuisine_type: List[str]
    food_type: List[str]
    flavor: List[str]
    dish_name: List[str]
    review_text: str
    metadata_quality: str
    
    # 這裡可以加一些 helper method，例如只拿前 50 個字的評論
    def get_short_review(self):
        return self.review_text[:50] + "..." if len(self.review_text) > 50 else self.review_text