import logging
from typing import Dict

from app.crawlers.bunjang_crawler import BunjangCrawler
from app.crawlers.joongna_crawler import JoongnaCrawler
from app.services.market.price_aggregator import PriceAggregator
from app.services.market.query_builder import QueryBuilder
from app.services.market.relevance_scorer import RelevanceScorer

logger = logging.getLogger(__name__)


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
        logger.info("market_queries=%s", queries)

        all_listings = []

        for crawler in self.crawlers:
            for query in queries:
                try:
                    results = await crawler.search(query)
                    logger.info(
                        "crawler=%s query='%s' raw_results=%d",
                        crawler.name, query, len(results),
                    )
                    all_listings.extend(results)
                except Exception as e:
                    logger.warning(
                        "crawler=%s query='%s' failed: %s",
                        crawler.name, query, e,
                    )
                    continue

        logger.info("total_raw_listings=%d", len(all_listings))

        filtered = []

        for listing in all_listings:
            score = RelevanceScorer.score(product, listing)
            logger.debug(
                "relevance_score=%.2f title=%s",
                score, listing.get("title", ""),
            )
            if score >= 0.3:
                filtered.append(listing)

        logger.info("filtered_listings=%d", len(filtered))

        price_context = PriceAggregator.aggregate(filtered)
        logger.info("price_context=%s", price_context)

        return {
            "crawler_sources": [crawler.name for crawler in self.crawlers],
            "price_band": price_context["price_band"],
            "median_price": price_context["median_price"],
            "sample_count": price_context["sample_count"],
        }
