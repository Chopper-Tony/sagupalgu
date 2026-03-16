from typing import Dict


class RelevanceScorer:
    @staticmethod
    def _normalize(text: str) -> str:
        return (text or "").lower().replace(" ", "").replace("-", "").replace("_", "")

    @classmethod
    def score(cls, product: Dict, listing: Dict) -> float:
        title = cls._normalize(listing.get("title", ""))

        brand = cls._normalize(product.get("brand", ""))
        model = cls._normalize(product.get("model", ""))
        storage = cls._normalize(product.get("storage", ""))

        score = 0.0

        # 모델이 가장 중요
        if model and model in title:
            score += 0.7

        # 브랜드는 보조
        if brand and brand in title:
            score += 0.2

        # 용량은 있으면 가산
        if storage and storage in title:
            score += 0.1

        return score