"""
경로: sagupalgu/test_bunjang_publish.py

번개장터 실제 게시 테스트
- 세션 파일 필요: sessions/bunjang_session.json
- 테스트용 임시 게시글 (올린 후 직접 삭제 필요)
"""
import asyncio
from pathlib import Path
from secondhand_publisher.core.models import ListingPackage, ProductCondition
from secondhand_publisher.publishers.bunjang import BunjangPublisher

async def main():
    publisher = BunjangPublisher(
        session_dir=Path("./sessions"),
        screenshot_dir=Path("./screenshots"),
        headless=False,
        slow_mo=400,
    )

    package = ListingPackage(
        product_name="테스트 상품",
        title="테스트 상품 (바로 삭제 예정)",
        description="자동화 테스트용 게시글입니다. 즉시 삭제할게요.",
        price=99999,
        category="디지털 > 스마트폰",
        condition=ProductCondition.GOOD,
        image_paths=[],
        tags=["테스트"],
        negotiable=False,
        shipping_available=True,
    )

    print("▶ 번개장터 게시 테스트 시작...")
    await publisher._launch()

    try:
        result = await publisher.publish(package)

        print(f"\n{'='*40}")
        if result.success:
            print(f"✅ 게시 성공!")
            print(f"   URL: {result.listing_url}")
            print(f"   ID:  {result.listing_id}")
            print(f"\n⚠️  테스트 게시글이므로 직접 삭제해주세요!")
        else:
            print(f"❌ 게시 실패: {result.error_message}")
    finally:
        await publisher._close()

if __name__ == "__main__":
    asyncio.run(main())