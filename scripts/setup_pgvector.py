"""
Supabase pgvector 셋업 + 초기 가격 데이터 시딩 스크립트.

사용법:
  1. Supabase 대시보드 → SQL Editor에서 migrations/001_pgvector_setup.sql 실행 (최초 1회)
  2. python scripts/setup_pgvector.py [--seed] [--query "아이폰 15"]

옵션:
  --seed          크롤링으로 초기 가격 데이터 수집 후 pgvector에 적재
  --query TEXT    시딩할 검색어 (기본: 인기 중고 카테고리 목록)
  --check         테이블/RPC 연결만 확인하고 종료
"""
import asyncio
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


SEED_QUERIES = [
    {"brand": "애플", "model": "아이폰 15 Pro", "category": "스마트폰"},
    {"brand": "애플", "model": "아이폰 15", "category": "스마트폰"},
    {"brand": "삼성", "model": "갤럭시 S24", "category": "스마트폰"},
    {"brand": "삼성", "model": "갤럭시 S23", "category": "스마트폰"},
    {"brand": "애플", "model": "맥북 에어 M3", "category": "노트북"},
    {"brand": "애플", "model": "맥북 프로 M3", "category": "노트북"},
    {"brand": "애플", "model": "에어팟 프로 2", "category": "이어폰"},
    {"brand": "소니", "model": "WH-1000XM5", "category": "헤드폰"},
    {"brand": "닌텐도", "model": "스위치 OLED", "category": "게임기"},
]


async def check_connection() -> bool:
    """테이블 및 RPC 함수 연결 확인."""
    from app.db.pgvector_store import is_table_ready
    from app.db.client import get_supabase

    print("── 연결 상태 확인 ───────────────────────────────────────")

    # 테이블 확인
    table_ok = await is_table_ready()
    print(f"  price_history 테이블: {'✅ 존재' if table_ok else '❌ 없음'}")

    if not table_ok:
        print()
        print("  [!] 테이블이 없습니다. 다음 순서로 생성하세요:")
        print("      1. Supabase 대시보드 → SQL Editor → New query")
        print("      2. migrations/001_pgvector_setup.sql 내용 붙여넣기 → Run")
        print("      3. 이 스크립트를 다시 실행하세요")
        return False

    # 레코드 수 확인
    try:
        sb = get_supabase()
        count_result = sb.table("price_history").select("id", count="exact").execute()
        count = count_result.count or 0
        print(f"  price_history 레코드 수: {count}건")
    except Exception as e:
        print(f"  레코드 수 조회 실패: {e}")

    # RPC 함수 확인 (임베딩 없이 테스트)
    try:
        sb = get_supabase()
        # 빈 벡터로 RPC 존재 여부만 확인
        sb.rpc("search_price_history", {
            "query_embedding": [0.0] * 1536,
            "match_threshold": 0.99,
            "match_count": 1,
        }).execute()
        print("  search_price_history RPC: ✅ 존재")
    except Exception as e:
        err_str = str(e)
        if "PGRST202" in err_str or "Could not find" in err_str:
            print("  search_price_history RPC: ❌ 없음 (SQL 마이그레이션 필요)")
            return False
        # 다른 에러는 함수는 있지만 파라미터 문제 등
        print(f"  search_price_history RPC: ✅ 존재 (테스트 응답: {err_str[:50]})")

    return True


async def seed_price_data(queries: list = None) -> None:
    """크롤링으로 가격 데이터 수집 후 pgvector에 시딩."""
    from app.core.config import settings
    from app.db.pgvector_store import insert_price_records

    if not settings.openai_api_key:
        print("[!] OPENAI_API_KEY 없음 — embedding 없이 키워드 검색 모드로 시딩")

    queries = queries or SEED_QUERIES
    print(f"\n── 가격 데이터 시딩 ({len(queries)}개 상품) ─────────────────────")

    try:
        from app.crawlers.market_crawler import MarketCrawler
        from app.services.market.query_builder import QueryBuilder
        from app.services.market.relevance_scorer import RelevanceScorer

        crawler = MarketCrawler()
        total_inserted = 0

        for q in queries:
            brand = q.get("brand", "")
            model = q.get("model", "")
            category = q.get("category", "")
            print(f"  크롤링: {brand} {model}...", end=" ", flush=True)

            try:
                query_strings = QueryBuilder.build_queries(q)
                records_to_insert = []

                for query_str in query_strings[:2]:
                    summary = await crawler.search(query_str, limit=20)
                    for item in summary.active_items:
                        listing = {
                            "title": item.title,
                            "price": item.price,
                            "platform": item.platform,
                            "url": item.url,
                        }
                        score = RelevanceScorer.score(q, listing)
                        if score >= 0.3:
                            records_to_insert.append({
                                "model": model,
                                "brand": brand,
                                "category": category,
                                "title": item.title,
                                "price": item.price,
                                "platform": item.platform,
                                "url": item.url,
                            })

                if records_to_insert:
                    inserted = await insert_price_records(
                        records_to_insert,
                        api_key=settings.openai_api_key or "",
                        skip_embedding=not bool(settings.openai_api_key),
                    )
                    total_inserted += inserted
                    print(f"{inserted}건 적재")
                else:
                    print("매물 없음")

            except Exception as e:
                print(f"실패: {e}")
                continue

        print(f"\n  총 {total_inserted}건 pgvector 시딩 완료")

    except Exception as e:
        print(f"\n[!] 크롤러 초기화 실패: {e}")
        print("  크롤러 없이 테스트 데이터로 대신 시딩합니다...")
        await _seed_test_data()


async def _seed_test_data() -> None:
    """크롤러 없을 때 테스트용 더미 데이터 시딩."""
    from app.core.config import settings
    from app.db.pgvector_store import insert_price_records

    test_records = [
        {"model": "아이폰 15 Pro", "brand": "애플", "category": "스마트폰",
         "title": "아이폰 15 Pro 128GB 블랙 판매", "price": 950000, "platform": "bunjang"},
        {"model": "아이폰 15 Pro", "brand": "애플", "category": "스마트폰",
         "title": "애플 아이폰15프로 256GB", "price": 1050000, "platform": "joongna"},
        {"model": "갤럭시 S24", "brand": "삼성", "category": "스마트폰",
         "title": "삼성 갤럭시S24 256GB 팬텀블랙", "price": 750000, "platform": "bunjang"},
        {"model": "맥북 에어 M3", "brand": "애플", "category": "노트북",
         "title": "맥북에어 M3 13인치 8GB 256GB", "price": 1300000, "platform": "bunjang"},
    ]

    inserted = await insert_price_records(
        test_records,
        api_key=settings.openai_api_key or "",
        skip_embedding=not bool(settings.openai_api_key),
    )
    print(f"  테스트 데이터 {inserted}건 시딩 완료")


async def main():
    import argparse
    parser = argparse.ArgumentParser(description="pgvector 셋업 및 시딩")
    parser.add_argument("--seed", action="store_true", help="가격 데이터 시딩")
    parser.add_argument("--check", action="store_true", help="연결 확인만")
    parser.add_argument("--query", type=str, default=None, help="시딩할 상품명")
    args = parser.parse_args()

    ok = await check_connection()

    if args.check or not ok:
        return

    if args.seed:
        queries = None
        if args.query:
            # 간단히 query string을 파싱해서 사용
            queries = [{"brand": "", "model": args.query, "category": ""}]
        await seed_price_data(queries)
    else:
        print("\n[INFO] --seed 옵션을 추가하면 가격 데이터를 수집·적재합니다.")
        print("  python scripts/setup_pgvector.py --seed")


if __name__ == "__main__":
    asyncio.run(main())
