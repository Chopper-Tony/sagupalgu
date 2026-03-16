def price_anomaly_filter(prices: list[int]) -> list[int]:
    cleaned = [p for p in prices if isinstance(p, int) and p > 0]
    if len(cleaned) < 4:
        return cleaned

    sorted_prices = sorted(cleaned)
    q1 = sorted_prices[len(sorted_prices) // 4]
    q3 = sorted_prices[(len(sorted_prices) * 3) // 4]
    iqr = q3 - q1
    lower = q1 - 1.5 * iqr
    upper = q3 + 1.5 * iqr

    return [p for p in sorted_prices if lower <= p <= upper]
