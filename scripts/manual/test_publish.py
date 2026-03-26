"""실제 게시 테스트 스크립트.

사전 조건:
  1. python scripts/manual/save_sessions.py 로 로그인 세션 저장 완료
  2. C:/Users/bonjo/Desktop/hahaha.jpg 이미지 파일 존재

사용법:
  python scripts/manual/test_publish.py          # 번개장터만
  python scripts/manual/test_publish.py joongna  # 중고나라만
  python scripts/manual/test_publish.py both     # 둘 다
"""
import asyncio
import os
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# headless=False로 브라우저 보이게
os.environ["PUBLISH_HEADLESS"] = "false"
os.environ["PUBLISH_SLOW_MO"] = "200"


async def test_bunjang():
    from app.publishers._legacy_compat import ListingPackage, ProductCondition, SellStrategy
    from app.publishers.bunjang_publisher import PatchedBunjangPublisher

    print("\n" + "=" * 60)
    print("  번개장터 실제 게시 테스트")
    print("=" * 60)

    package = ListingPackage(
        product_name="아이폰 15 Pro",
        category="스마트폰",
        condition=ProductCondition.GOOD,
        price=824000,
        title="[테스트] 애플 아이폰 15 Pro 256GB 실버 상태 최상",
        description=(
            "애플 아이폰 15 Pro 256GB 실버 모델입니다. "
            "외관에 미세한 스크래치 없이 깨끗하며 배터리 건강 상태 95% 이상 유지 중입니다. "
            "사용 기간은 약 3개월로 매우 짧습니다. "
            "구성품은 정품 박스, 충전기, USB-C 케이블 포함되어 있습니다. "
            "직거래 및 택배 거래 모두 가능합니다. "
            "⚠️ 이 게시글은 자동화 테스트입니다. 실제 판매 아닙니다."
        ),
        tags=["아이폰15Pro", "256GB", "실버", "최상태", "테스트"],
        negotiable=True,
        shipping_available=False,
        shipping_fee=0,
        meet_location="",
        image_paths=[Path("C:/Users/bonjo/Desktop/hahaha.jpg")],
        strategy=SellStrategy.NORMAL,
    )

    publisher = PatchedBunjangPublisher(
        headless=False,
        slow_mo=200,
    )

    result = await publisher.run(package=package, phone="", password="")

    print(f"\n  성공: {result.success}")
    if result.success:
        print(f"  URL: {result.listing_url}")
        print(f"  ID: {result.listing_id}")
    else:
        print(f"  에러: {result.error_message}")
    if result.screenshot_path:
        print(f"  스크린샷: {result.screenshot_path}")

    return result


async def test_joongna():
    from app.publishers._legacy_compat import ListingPackage, ProductCondition, SellStrategy
    from app.publishers._legacy_compat import LegacyJoongnaPublisher

    print("\n" + "=" * 60)
    print("  중고나라 실제 게시 테스트")
    print("=" * 60)

    package = ListingPackage(
        product_name="아이폰 15 Pro",
        category="스마트폰",
        condition=ProductCondition.GOOD,
        price=824000,
        title="[테스트] 애플 아이폰 15 Pro 256GB 실버 상태 최상",
        description=(
            "애플 아이폰 15 Pro 256GB 실버 모델입니다. "
            "외관에 미세한 스크래치 없이 깨끗하며 배터리 건강 상태 95% 이상 유지 중입니다. "
            "⚠️ 이 게시글은 자동화 테스트입니다. 실제 판매 아닙니다."
        ),
        tags=["아이폰15Pro", "256GB", "실버", "최상태", "테스트"],
        negotiable=True,
        shipping_available=False,
        shipping_fee=0,
        meet_location="",
        image_paths=[Path("C:/Users/bonjo/Desktop/hahaha.jpg")],
        strategy=SellStrategy.NORMAL,
    )

    publisher = LegacyJoongnaPublisher(
        headless=False,
        slow_mo=200,
    )

    result = await publisher.run(package=package, phone="", password="")

    print(f"\n  성공: {result.success}")
    if result.success:
        print(f"  URL: {result.listing_url}")
        print(f"  ID: {result.listing_id}")
    else:
        print(f"  에러: {result.error_message}")
    if result.screenshot_path:
        print(f"  스크린샷: {result.screenshot_path}")

    return result


async def main():
    target = sys.argv[1] if len(sys.argv) > 1 else "bunjang"

    if target == "bunjang":
        await test_bunjang()
    elif target == "joongna":
        await test_joongna()
    elif target == "both":
        await test_bunjang()
        await test_joongna()
    else:
        print(f"알 수 없는 대상: {target}")
        print("사용법: python scripts/manual/test_publish.py [bunjang|joongna|both]")

    print("\n⚠️ 테스트 게시글이라면 각 플랫폼에서 직접 삭제해주세요!")


if __name__ == "__main__":
    asyncio.run(main())
