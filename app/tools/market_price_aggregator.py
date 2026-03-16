from statistics import median

def market_price_aggregator(crawler_results: list[dict]) -> dict:
    prices: list[int] = []
    for result in crawler_results:
        prices.extend([p for p in result.get("prices", []) if isinstance(p, int) and p > 0])

    if not prices:
        return {"price_band": [0, 0], "median_price": 0, "sample_count": 0}

    sorted_prices = sorted(prices)
    return {
        "price_band": [sorted_prices[0], sorted_prices[-1]],
        "median_price": int(median(sorted_prices)),
        "sample_count": len(sorted_prices),
    }
