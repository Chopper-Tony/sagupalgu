from app.crawlers.market_crawler import MarketCrawler, PriceSummary


class MarketService:
    def __init__(self):
        self.crawler = MarketCrawler()

    async def build_market_context(self, confirmed_product: dict) -> dict:
        brand = confirmed_product.get("brand", "Unknown")
        model = confirmed_product.get("model", "상품")
        category = confirmed_product.get("category", "unknown")

        query_parts = [brand, model]
        query = " ".join(part for part in query_parts if part and part != "Unknown").strip()

        if not query:
            query = category if category and category != "unknown" else "중고 상품"

        summary: PriceSummary = await self.crawler.search(
            query=query,
            limit=20,
            platforms=("bunjang", "joongna"),
        )

        active_items = summary.active_items
        prices = [item.price for item in active_items if item.price > 0]

        if prices:
            price_band = [min(prices), max(prices)]
            median_price = sorted(prices)[len(prices) // 2]
            sample_count = len(prices)
            rag_summary = (
                f"{query} 기준 활성 매물 {sample_count}건, "
                f"최저 {price_band[0]:,}원 ~ 최고 {price_band[1]:,}원"
            )
        else:
            price_band = [0, 0]
            median_price = 0
            sample_count = 0
            rag_summary = f"{query} 기준 유효한 시세 데이터를 찾지 못했습니다"

        return {
            "analysis_source": "crawler",
            "crawler_sources": ["joongna", "bunjang"],
            "price_band": price_band,
            "median_price": median_price,
            "sample_count": sample_count,
            "rag_summary": rag_summary,
            "query": query,
            "items": [
                {
                    "platform": item.platform,
                    "title": item.title,
                    "price": item.price,
                    "condition": item.condition,
                    "url": item.url,
                    "sold": item.sold,
                    "created_at": item.created_at,
                }
                for item in active_items[:10]
            ],
        }