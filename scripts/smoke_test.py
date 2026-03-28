"""
Staging/Prod Smoke Test 스크립트.

배포 후 핵심 엔드포인트 동작을 자동 검증한다.

사용법:
  python scripts/smoke_test.py                          # localhost:8000
  python scripts/smoke_test.py --base-url https://api.sagupalgu.com
"""
from __future__ import annotations

import sys
import json


def run_smoke_tests(base_url: str) -> list[dict]:
    """핵심 엔드포인트를 순차 호출하여 검증한다."""
    import httpx

    results: list[dict] = []
    client = httpx.Client(base_url=base_url, timeout=10.0)

    # 1. Health Live
    try:
        r = client.get("/health/live")
        results.append({
            "test": "health_live",
            "passed": r.status_code == 200 and r.json().get("status") == "ok",
            "status_code": r.status_code,
        })
    except Exception as e:
        results.append({"test": "health_live", "passed": False, "error": str(e)})

    # 2. Health Ready
    try:
        r = client.get("/health/ready")
        data = r.json()
        results.append({
            "test": "health_ready",
            "passed": r.status_code == 200 and "checks" in data,
            "status_code": r.status_code,
            "status": data.get("status"),
        })
    except Exception as e:
        results.append({"test": "health_ready", "passed": False, "error": str(e)})

    # 3. Health Deep
    try:
        r = client.get("/health/deep")
        results.append({
            "test": "health_deep",
            "passed": r.status_code == 200 and "llm_reachable" in r.json(),
            "status_code": r.status_code,
        })
    except Exception as e:
        results.append({"test": "health_deep", "passed": False, "error": str(e)})

    # 4. Session Create
    try:
        r = client.post(
            "/api/v1/sessions",
            headers={"X-Dev-User-Id": "smoke-test-user"},
        )
        results.append({
            "test": "create_session",
            "passed": r.status_code == 200 and "session_id" in r.json(),
            "status_code": r.status_code,
        })
    except Exception as e:
        results.append({"test": "create_session", "passed": False, "error": str(e)})

    # 5. Session Get (존재하지 않는 ID → 404)
    try:
        r = client.get(
            "/api/v1/sessions/nonexistent-smoke-test",
            headers={"X-Dev-User-Id": "smoke-test-user"},
        )
        results.append({
            "test": "get_session_404",
            "passed": r.status_code == 404,
            "status_code": r.status_code,
        })
    except Exception as e:
        results.append({"test": "get_session_404", "passed": False, "error": str(e)})

    client.close()
    return results


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Smoke Test")
    parser.add_argument("--base-url", default="http://localhost:8000", help="API base URL")
    parser.add_argument("--json", action="store_true", help="JSON 출력")
    args = parser.parse_args()

    print(f"== Smoke Test ({args.base_url}) ==\n")

    results = run_smoke_tests(args.base_url)

    if args.json:
        print(json.dumps(results, indent=2, ensure_ascii=False))
        return

    passed = sum(1 for r in results if r["passed"])
    total = len(results)

    for r in results:
        icon = "PASS" if r["passed"] else "FAIL"
        detail = f"status={r.get('status_code', '?')}"
        if r.get("error"):
            detail = f"error={r['error'][:60]}"
        print(f"  [{icon}] {r['test']} — {detail}")

    print(f"\n  결과: {passed}/{total} 통과")

    if passed < total:
        sys.exit(1)


if __name__ == "__main__":
    main()
