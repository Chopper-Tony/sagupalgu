from pathlib import Path
import sys
from pprint import pprint

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.graph.seller_copilot_runner import seller_copilot_runner


def main():
    result = seller_copilot_runner.run(
        session_id="test-session-001",
        image_paths=["C:/Users/bonjo/Desktop/hahaha.jpg"],
        selected_platforms=["bunjang", "joongna"],
        user_product_input={
            "brand": "애플",
            "model": "아이폰 15 Pro",
            "category": "스마트폰",
        },
        market_context={
            "price_band": [650000, 1150000],
            "median_price": 850000,
            "sample_count": 26,
            "crawler_sources": ["joongna", "bunjang"],
        },
    )

    print("\n=== FINAL STATE ===")
    pprint(result)

    print("\n=== SUMMARY ===")
    print("status:", result.get("status"))
    print("checkpoint:", result.get("checkpoint"))
    print("needs_user_input:", result.get("needs_user_input"))
    print("confirmed_product:", result.get("confirmed_product"))
    print("strategy:", result.get("strategy"))
    print("canonical_listing:", result.get("canonical_listing"))
    print("platform_packages:", result.get("platform_packages"))
    print("validation_result:", result.get("validation_result"))
    print("debug_logs:", result.get("debug_logs"))


if __name__ == "__main__":
    main()