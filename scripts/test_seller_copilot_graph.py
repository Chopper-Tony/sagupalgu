import asyncio
import sys
from pathlib import Path
from pprint import pprint

# ── 한국어 출력 인코딩 수정 (Windows CP949 → UTF-8) ──────────────────
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

# Windows Playwright 호환 이벤트 루프
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.graph.seller_copilot_runner import seller_copilot_runner


def main():
    # 그래프가 내부적으로 publish까지 실행함 (publish_node가 graph에 포함됨)
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
    print("status           :", result.get("status"))
    print("checkpoint       :", result.get("checkpoint"))
    print("needs_user_input :", result.get("needs_user_input"))
    print("confirmed_product:", result.get("confirmed_product"))
    print("strategy         :", result.get("strategy"))
    print("canonical_listing:", result.get("canonical_listing"))
    print("platform_packages:", result.get("platform_packages"))
    print("validation_result:", result.get("validation_result"))
    print("publish_results  :", result.get("publish_results"))
    print("patch_suggestions:", result.get("patch_suggestions"))
    print("debug_logs       :", result.get("debug_logs"))

    # ── 게시 결과 출력 ────────────────────────────────────────────────
    publish_results = result.get("publish_results") or {}
    if not publish_results:
        print("\n[INFO] publish_results 없음 — graph가 publish_node에 도달하지 못했거나 건너뜀")
        return

    print("\n=== PUBLISH RESULTS ===")
    for platform, r in publish_results.items():
        if r.get("success"):
            print(f"  [{platform}] 게시 성공!")
            print(f"     URL : {r.get('external_url')}")
            print(f"     ID  : {r.get('external_listing_id')}")
            if r.get("evidence_path"):
                print(f"     스크린샷: {r.get('evidence_path')}")
        else:
            print(f"  [{platform}] 게시 실패: {r.get('error_message')}")

    # 패치 제안이 있으면 출력
    patches = result.get("patch_suggestions") or []
    if patches:
        print("\n=== PATCH SUGGESTIONS (auto_patch_tool) ===")
        for p in patches:
            print(f"  type={p.get('type')} | 실행가능={p.get('auto_executable')} | {p.get('action')}")

    print("\n[INFO] 테스트 게시글이라면 각 플랫폼에서 직접 삭제해주세요!")


if __name__ == "__main__":
    main()
