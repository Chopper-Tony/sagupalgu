# app/services/market/price_aggregator.py

from typing import List, Dict
import statistics


class PriceAggregator:
    """
    크롤링된 가격 데이터에서 시세 계산
    """

    @staticmethod
    def aggregate(listings: List[Dict]) -> Dict:
        prices = [
            l.get("price")
            for l in listings
            if isinstance(l.get("price"), (int, float))
        ]

        if not prices:
            return {
                "median_price": None,
                "price_band": None,
                "sample_count": 0,
            }

        median = statistics.median(prices)

        # 이상치 제거
        filtered = [
            p for p in prices
            if 0.5 * median <= p <= 1.5 * median
        ]

        if not filtered:
            filtered = prices

        band = [min(filtered), max(filtered)]

        return {
            "median_price": int(statistics.median(filtered)),
            "price_band": band,
            "sample_count": len(filtered),
        }