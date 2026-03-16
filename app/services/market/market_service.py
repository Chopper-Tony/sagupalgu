from typing import Dict

from app.crawlers.bunjang_crawler import BunjangCrawler
from app.crawlers.joongna_crawler import JoongnaCrawler
from app.services.market.price_aggregator import PriceAggregator
from app.services.market.query_builder import QueryBuilder
from app.services.market.relevance_scorer import RelevanceScorer


class MarketService:
    """
    Market intelligence orchestration
    MVP 활성 플랫폼:
    - joongna
    - bunjang
    """

    def __init__(self):
        self.crawlers = [
            JoongnaCrawler(),
            BunjangCrawler(),
        ]

    async def analyze_market(self, product: Dict) -> Dict:
        queries = QueryBuilder.build_queries(product)
        print(f"[MarketService] queries={queries}")

        all_listings = []

        for crawler in self.crawlers:
            for query in queries:
                try:
                    results = await crawler.search(query)
                    print(
                        f"[MarketService] crawler={crawler.name} query='{query}' raw_results={len(results)}"
                    )
                    all_listings.extend(results)
                except Exception as e:
                    print(
                        f"[MarketService] crawler={crawler.name} query='{query}' failed: {e}"
                    )
                    continue

        print(f"[MarketService] total_raw_listings={len(all_listings)}")

        filtered = []

        for listing in all_listings:
            score = RelevanceScorer.score(product, listing)
            print(
                f"[MarketService] score={score:.2f} title={listing.get('title', '')}"
            )
            if score >= 0.3:
                filtered.append(listing)

        print(f"[MarketService] filtered_listings={len(filtered)}")

        price_context = PriceAggregator.aggregate(filtered)
        print(f"[MarketService] price_context={price_context}")

        return {
            "crawler_sources": [crawler.name for crawler in self.crawlers],
            "price_band": price_context["price_band"],
            "median_price": price_context["median_price"],
            "sample_count": price_context["sample_count"],
        }