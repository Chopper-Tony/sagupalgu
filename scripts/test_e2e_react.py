"""E2E 실테스트: _run_async 수정 후 ReAct 에이전트 정상 동작 확인.

서버가 http://localhost:8000에서 실행 중이어야 합니다.
python scripts/test_e2e_react.py
"""
import json
import os
import sys
import tempfile
import time

import httpx

BASE = "http://127.0.0.1:8000/api/v1"
TIMEOUT = 120.0
IMG_PATH = os.path.join(tempfile.gettempdir(), "test_iphone.jpg")


def step(name, fn):
    sys.stdout.write(f"\n{'='*60}\n  {name}\n{'='*60}\n")
    sys.stdout.flush()
    start = time.time()
    result = fn()
    elapsed = time.time() - start
    status = result.get("status", "N/A")
    sys.stdout.write(f"  [{elapsed:.1f}s] status: {status}\n")
    if result.get("last_error"):
        sys.stdout.write(f"  error: {result['last_error']}\n")
    sys.stdout.flush()
    return result


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    client = httpx.Client(timeout=TIMEOUT)

    # 1. 세션 생성
    d = step("1. 세션 생성", lambda: client.post(f"{BASE}/sessions").json())
    sid = d["session_id"]
    print(f"  session_id: {sid}")

    # 2. 이미지 업로드
    if not os.path.exists(IMG_PATH):
        print(f"  이미지 없음: {IMG_PATH}")
        print("  curl로 먼저 다운로드하세요")
        return
    with open(IMG_PATH, "rb") as f:
        d = step("2. 이미지 업로드", lambda: client.post(
            f"{BASE}/sessions/{sid}/images",
            files={"files": ("test.jpg", f, "image/jpeg")},
        ).json())

    # 3. 분석
    d = step("3. Vision 분석", lambda: client.post(
        f"{BASE}/sessions/{sid}/analyze",
    ).json())
    for c in (d.get("product_candidates") or []):
        print(f"  후보: {c.get('brand')} {c.get('model')} (confidence: {c.get('confidence')})")

    # 4. 상품 확정
    d = step("4. 상품 확정", lambda: client.post(
        f"{BASE}/sessions/{sid}/provide-product-info",
        json={"model": "iPhone 15 Pro", "brand": "Apple", "category": "smartphone"},
    ).json())

    # 5. 판매글 생성 (ReAct 핵심)
    print("\n  *** 핵심 테스트: ReAct 에이전트 동작 확인 ***")
    d = step("5. 판매글 생성", lambda: client.post(
        f"{BASE}/sessions/{sid}/generate-listing",
        timeout=180,
    ).json())

    cl = d.get("canonical_listing") or {}
    mc = d.get("market_context") or {}
    print(f"  제목: {cl.get('title')}")
    print(f"  가격: {cl.get('price')}")
    print(f"  태그: {cl.get('tags')}")
    print(f"  설명: {(cl.get('description') or '')[:150]}...")
    print(f"  시세 중앙값: {mc.get('median_price')}")
    print(f"  시세 샘플: {mc.get('sample_count')}")

    # tool_calls 확인
    trace = d.get("agent_trace") or {}
    tc = trace.get("tool_calls") or []
    print(f"  tool_calls: {len(tc)}개")
    for t in tc[:5]:
        if isinstance(t, dict):
            print(f"    {t.get('tool_name', 'unknown')}: {json.dumps(t.get('result', ''), ensure_ascii=False)[:80]}")
        else:
            print(f"    {str(t)[:80]}")

    # 6. 게시 준비
    d = step("6. 게시 준비", lambda: client.post(
        f"{BASE}/sessions/{sid}/prepare-publish",
        json={"platform_targets": ["bunjang"]},
    ).json())

    # 서버 로그에서 fallback 여부 확인
    print(f"\n{'='*60}")
    print("  결과 요약")
    print(f"{'='*60}")
    print(f"  최종 상태: {d.get('status')}")
    price = (d.get("canonical_listing") or {}).get("price", 0)
    print(f"  최종 가격: {price:,}원" if price else "  최종 가격: 0원 (시세 크롤링 실패)")

    client.close()


if __name__ == "__main__":
    main()
