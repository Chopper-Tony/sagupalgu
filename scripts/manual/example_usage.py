"""
전체 통합 예제
=============
사용 방법:

  1. 환경 변수 설정:
     export BUNJANG_PHONE="010XXXXXXXX"
     export BUNJANG_PW="your_password"
     export JOONGNA_ID="naver_or_joongna_id"
     export JOONGNA_PW="your_password"

  2. 실행:
     python example_usage.py

워크플로우:
  [사진 경로] → [ListingPackage 생성]
    → [MarketCrawler로 시세 조회]
    → [가격 전략 적용]
    → [번개장터 + 중고나라 동시 게시]
    → [결과 출력]
"""
import asyncio
import logging
import os
from pathlib import Path

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)

from secondhand_publisher.core.models import (
    ListingPackage, ProductCondition, SellStrategy, Platform
)
from secondhand_publisher.publishers.bunjang import BunjangPublisher
from secondhand_publisher.publishers.joongna import JoongnaPublisher
from secondhand_publisher.publishers.daangn import DaangnPublisher
from secondhand_publisher.publishers.orchestrator import (
    PublisherOrchestrator, PlatformCredentials
)
from secondhand_publisher.utils.market_crawler import MarketCrawler


async def demo_crawl_prices():
    """시세 조회 데모"""
    print("\n" + "="*50)
    print("📊 시세 조회 데모")
    print("="*50)

    crawler = MarketCrawler()
    summary = await crawler.search("아이폰 15 프로 256GB", limit=15)

    print(f"\n검색어: {summary.query}")
    print(f"수집 매물: {len(summary.items)}개 (판매중: {len(summary.active_items)}개)")
    print(f"평균 시세:  {summary.avg_price:>10,}원")
    print(f"최저 시세:  {summary.min_price:>10,}원")
    print(f"최고 시세:  {summary.max_price:>10,}원")
    print()
    print("전략별 추천 가격:")
    print(f"  빠른 판매:   {summary.recommended_price('fast'):>10,}원 (시세 -10%)")
    print(f"  적정가:      {summary.recommended_price('normal'):>10,}원 (시세 그대로)")
    print(f"  최대 이익:   {summary.recommended_price('max_profit'):>10,}원 (시세 +5%)")

    print("\n상위 5개 매물:")
    for item in summary.active_items[:5]:
        status = "판매중" if not item.sold else "판매완료"
        print(f"  [{item.platform}] {item.price:>8,}원 | {item.title[:30]}")

    return summary


async def demo_publish():
    """게시 자동화 데모"""
    print("\n" + "="*50)
    print("🚀 게시 자동화 데모")
    print("="*50)

    # ─── 1. 시세 조회 ───
    crawler = MarketCrawler()
    summary = await crawler.search("AirPods Pro 2세대")
    recommended_price = summary.recommended_price("normal")
    print(f"추천 가격: {recommended_price:,}원")

    # ─── 2. ListingPackage 구성 ───
    # (실제로는 Vision AI + Copywriting Agent가 생성)
    package = ListingPackage(
        product_name="Apple AirPods Pro 2세대",
        category="디지털기기 > 이어폰/헤드폰",
        condition=ProductCondition.LIKE_NEW,
        price=recommended_price or 180000,

        title="[거의새것] 에어팟 프로 2세대 MagSafe 충전케이스 포함",
        description=(
            "■ 상품 정보\n"
            "에어팟 프로 2세대 판매합니다.\n"
            "- 구매 후 5회 미만 사용\n"
            "- 충전케이스 포함, 케이블 미포함\n"
            "- 스크래치 전혀 없는 깨끗한 상태\n\n"
            "■ 구성품\n"
            "본체, 충전케이스, 이어팁(S/M/L) 풀셋\n\n"
            "■ 거래 안내\n"
            "직거래 우선, 택배 가능 (선불)\n"
            "가격 제안 환영합니다 :)"
        ),
        tags=["에어팟프로", "에어팟프로2세대", "애플"],

        negotiable=True,
        shipping_available=True,
        shipping_fee=3500,

        # 이미지 경로 (실제 파일로 대체)
        image_paths=[
            Path("./test_images/airpods_front.jpg"),
            Path("./test_images/airpods_back.jpg"),
        ],

        strategy=SellStrategy.NORMAL,

        # 플랫폼별 제목 오버라이드
        platform_overrides={
            "번개장터": {
                "title": "에어팟프로 2세대 거의새것 팔아요",
            },
            "중고나라": {
                "title": "[직거래/택배] 에어팟 프로 2세대 미개봉급",
            },
        }
    )

    print(f"\n상품: {package.product_name}")
    print(f"가격: {package.price:,}원")
    print(f"상태: {package.condition.value}")

    # ─── 3. 계정 정보 (환경변수에서 로드) ───
    credentials = PlatformCredentials(
        bunjang_phone=os.getenv("BUNJANG_PHONE", ""),
        bunjang_password=os.getenv("BUNJANG_PW", ""),
        joongna_id=os.getenv("JOONGNA_ID", ""),
        joongna_password=os.getenv("JOONGNA_PW", ""),
    )

    # 계정 정보가 없으면 dry-run
    if not credentials.bunjang_phone and not credentials.joongna_id:
        print("\n⚠️  계정 정보 없음 → dry-run 모드 (실제 게시 안 함)")
        print("실제 게시를 위해 환경변수를 설정하세요:")
        print("  export BUNJANG_PHONE='010XXXXXXXX'")
        print("  export BUNJANG_PW='your_password'")
        return

    # ─── 4. 게시 실행 ───
    orchestrator = PublisherOrchestrator(
        credentials=credentials,
        headless=True,        # False로 하면 브라우저 화면 보임
        concurrent=False,     # 순차 게시
    )

    results = await orchestrator.publish_all(package)

    # ─── 5. 결과 출력 ───
    print("\n📋 게시 결과:")
    for platform, result in results.items():
        if result.success:
            print(f"  ✅ {platform.value}: {result.listing_url}")
        else:
            print(f"  ❌ {platform.value}: {result.error_message}")
            if result.screenshot_path:
                print(f"     스크린샷: {result.screenshot_path}")


async def demo_single_platform():
    """단일 플랫폼 테스트 (번개장터만)"""
    print("\n" + "="*50)
    print("🔧 번개장터 단일 테스트")
    print("="*50)

    package = ListingPackage(
        product_name="테스트 상품",
        category="디지털기기 > 스마트폰",
        condition=ProductCondition.GOOD,
        price=100000,
        title="테스트 판매글입니다",
        description="테스트용 상품입니다.",
        image_paths=[],
    )

    publisher = BunjangPublisher(headless=False)  # 헤드풀 모드로 확인
    result = await publisher.run(
        package=package,
        phone=os.getenv("BUNJANG_PHONE", ""),
        password=os.getenv("BUNJANG_PW", ""),
    )
    print(result)


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "crawl":
        asyncio.run(demo_crawl_prices())
    elif len(sys.argv) > 1 and sys.argv[1] == "single":
        asyncio.run(demo_single_platform())
    else:
        asyncio.run(demo_publish())
