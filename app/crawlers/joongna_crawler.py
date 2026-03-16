from legacy_spikes.secondhand_publisher.utils.market_crawler import MarketCrawler


def _build_query(confirmed_product: dict) -> str:
    return " ".join(
        [
            confirmed_product.get("brand", ""),
            confirmed_product.get("model", ""),
            confirmed_product.get("storage", ""),
        ]
    ).strip() or confirmed_product.get("model", "중고 상품")


async def joongna_crawler_tool(confirmed_product: dict) -> dict:
    crawler = MarketCrawler()
    summary = await crawler.search(
        _build_query(confirmed_product),
        limit=20,
        platforms=("joongna",),
    )
    prices = [item.price for item in summary.active_items if item.platform == "중고나라"]
    return {
        "source": "joongna",
        "prices": prices,
        "sample_count": len(prices),
    }


class JoongnaCrawler:
    name = "joongna"

    async def search(self, query: str) -> list[dict]:
        crawler = MarketCrawler()
        summary = await crawler.search(query, limit=20, platforms=("joongna",))

        results = []
        for item in summary.active_items:
            if item.platform != "중고나라":
                continue

            results.append(
                {
                    "title": item.title,
                    "price": item.price,
                    "url": item.url,
                    "platform": "joongna",
                    "source": "joongna",
                }
            )

        return results