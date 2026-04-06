"""
게시 성공률 측정 배치 테스트.
10회 연속 파이프라인 실행 → 실제 게시 포함 → 결과 집계.
"""
import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

BASE = "http://127.0.0.1:8000/api/v1"
DELAY_BETWEEN_RUNS = 10  # 회차 간 대기 (초)

IMAGES = [
    "uploads/089475dc-c5aa-48c6-8c9a-76514d50c44f/f14c01cf52dd44c5a8988052ff15ddf3.jpg",
    "uploads/0b490bcb-3d51-446c-b123-376cdc552f84/038e8072079844c9b6a42e1b05153a0c.png",
    "uploads/1227c98f-e4a7-434e-8df0-e4bab684f6bb/36c5738de3f441f4830905c63ce4d760.jpg",
    "uploads/1b3ecc46-62af-4623-81f9-e101934046a8/81ef9878c954470886cc0780f4212a40.jpg",
    "uploads/1cbdc214-7474-4b42-9bb0-fb9cadf3772d/3617208b27b749c4903fd6a19dc964d1.jpg",
]

STEPS = [
    "health", "create_session", "upload_image", "analyze",
    "confirm_product", "generate_listing", "prepare_publish", "publish",
]


async def run_single(client, image_path: str, run_id: int) -> dict:
    """단일 파이프라인 실행. 각 단계 성공/실패/시간 기록."""
    result = {
        "run": run_id,
        "image": image_path,
        "steps": {},
        "failed_at": None,
        "total_time": 0,
        "publish_success": False,
        "publish_platforms": [],
    }
    session_id = ""
    t0 = time.time()

    async def step(name, coro):
        """단계 실행 래퍼."""
        st = time.time()
        try:
            data = await coro
            elapsed = time.time() - st
            result["steps"][name] = {"success": True, "elapsed": round(elapsed, 1)}
            return data
        except Exception as e:
            elapsed = time.time() - st
            result["steps"][name] = {"success": False, "elapsed": round(elapsed, 1), "error": str(e)[:200]}
            result["failed_at"] = name
            raise

    try:
        # 0. health
        async def do_health():
            r = await client.get(f"{BASE.replace('/api/v1', '')}/health/ready")
            r.raise_for_status()
            return r.json()
        await step("health", do_health())

        # 1. create session
        async def do_create():
            r = await client.post(f"{BASE}/sessions")
            r.raise_for_status()
            return r.json()
        data = await step("create_session", do_create())
        session_id = data["session_id"]

        # 2. upload image
        async def do_upload():
            with open(image_path, "rb") as f:
                files = {"files": (Path(image_path).name, f, "image/jpeg")}
                r = await client.post(f"{BASE}/sessions/{session_id}/images", files=files)
            r.raise_for_status()
            return r.json()
        await step("upload_image", do_upload())

        # 3. analyze
        async def do_analyze():
            r = await client.post(f"{BASE}/sessions/{session_id}/analyze")
            r.raise_for_status()
            return r.json()
        data = await step("analyze", do_analyze())

        # 4. confirm product
        async def do_confirm():
            candidates = data.get("product_candidates", [])
            if candidates and candidates[0].get("confidence", 0) >= 0.6:
                r = await client.post(f"{BASE}/sessions/{session_id}/confirm-product",
                                      json={"candidate_index": 0})
            else:
                r = await client.post(f"{BASE}/sessions/{session_id}/provide-product-info",
                                      json={"brand": "테스트", "model": "테스트 상품", "category": "기타"})
            r.raise_for_status()
            return r.json()
        await step("confirm_product", do_confirm())

        # 5. generate listing
        async def do_generate():
            r = await client.post(f"{BASE}/sessions/{session_id}/generate-listing")
            r.raise_for_status()
            return r.json()
        gen_data = await step("generate_listing", do_generate())

        # 6. prepare publish
        async def do_prepare():
            r = await client.post(f"{BASE}/sessions/{session_id}/prepare-publish",
                                  json={"platform_targets": ["bunjang"]})
            r.raise_for_status()
            return r.json()
        await step("prepare_publish", do_prepare())

        # 7. publish
        async def do_publish():
            r = await client.post(f"{BASE}/sessions/{session_id}/publish")
            r.raise_for_status()
            return r.json()
        pub_data = await step("publish", do_publish())

        # 게시 결과 분석
        platform_results = pub_data.get("platform_results", [])
        for pr in platform_results:
            result["publish_platforms"].append({
                "platform": pr.get("platform"),
                "success": pr.get("success", False),
                "url": pr.get("listing_url", ""),
                "error": pr.get("error_message", ""),
            })
        result["publish_success"] = any(pr.get("success") for pr in platform_results)

    except Exception:
        pass  # failed_at already set

    result["total_time"] = round(time.time() - t0, 1)
    return result


async def main():
    import httpx

    print("=" * 60)
    print("  게시 성공률 배치 테스트 (5회, 실제 게시 포함)")
    print("=" * 60)

    all_results = []

    async with httpx.AsyncClient(timeout=300) as client:
        for i, img in enumerate(IMAGES):
            print(f"\n{'#' * 60}")
            print(f"  Run {i+1}/{len(IMAGES)} | 이미지: {Path(img).name}")
            print(f"{'#' * 60}")

            result = await run_single(client, img, i + 1)
            all_results.append(result)

            # 진행 상황 출력
            for sname in STEPS:
                info = result["steps"].get(sname)
                if info:
                    icon = "[OK]" if info["success"] else "[FAIL]"
                    err = f" - {info.get('error', '')}" if not info["success"] else ""
                    print(f"  {icon} {sname:<20} {info['elapsed']:>6.1f}s{err}")

            if result["publish_success"]:
                for pr in result["publish_platforms"]:
                    if pr["success"]:
                        print(f"  >>> {pr['platform']}: {pr['url']}")

            print(f"  총 소요: {result['total_time']}s | 게시: {'성공' if result['publish_success'] else '실패'}")

            # 마지막 회차가 아니면 대기
            if i < len(IMAGES) - 1:
                print(f"\n  {DELAY_BETWEEN_RUNS}초 대기...")
                await asyncio.sleep(DELAY_BETWEEN_RUNS)

    # ── 최종 리포트 ──
    print("\n" + "=" * 60)
    print("  최종 결과 리포트")
    print("=" * 60)

    total = len(all_results)
    pipeline_success = sum(1 for r in all_results if r["failed_at"] is None)
    publish_success = sum(1 for r in all_results if r["publish_success"])

    # 단계별 성공률
    print("\n[단계별 성공률]")
    for sname in STEPS:
        attempted = sum(1 for r in all_results if sname in r["steps"])
        succeeded = sum(1 for r in all_results if r["steps"].get(sname, {}).get("success", False))
        rate = (succeeded / attempted * 100) if attempted > 0 else 0
        avg_time = 0
        times = [r["steps"][sname]["elapsed"] for r in all_results if sname in r["steps"] and r["steps"][sname]["success"]]
        if times:
            avg_time = sum(times) / len(times)
        print(f"  {sname:<20} {succeeded}/{attempted} ({rate:.0f}%)  avg {avg_time:.1f}s")

    # 실패 원인 분석
    failures = [r for r in all_results if r["failed_at"]]
    if failures:
        print(f"\n[실패 원인]")
        for r in failures:
            err = r["steps"].get(r["failed_at"], {}).get("error", "?")
            print(f"  Run {r['run']}: {r['failed_at']} - {err[:100]}")

    # 게시 플랫폼별 결과
    print(f"\n[게시 결과]")
    platform_stats = {}
    for r in all_results:
        for pr in r["publish_platforms"]:
            p = pr["platform"]
            if p not in platform_stats:
                platform_stats[p] = {"success": 0, "fail": 0, "errors": []}
            if pr["success"]:
                platform_stats[p]["success"] += 1
            else:
                platform_stats[p]["fail"] += 1
                if pr["error"]:
                    platform_stats[p]["errors"].append(pr["error"][:80])

    for p, stats in platform_stats.items():
        total_p = stats["success"] + stats["fail"]
        rate = stats["success"] / total_p * 100 if total_p > 0 else 0
        print(f"  {p}: {stats['success']}/{total_p} ({rate:.0f}%)")
        for err in set(stats["errors"]):
            print(f"    실패: {err}")

    # 요약
    avg_total = sum(r["total_time"] for r in all_results) / total if total > 0 else 0
    print(f"\n[요약]")
    print(f"  파이프라인 성공: {pipeline_success}/{total} ({pipeline_success/total*100:.0f}%)")
    print(f"  게시 성공:       {publish_success}/{total} ({publish_success/total*100:.0f}%)")
    print(f"  평균 소요시간:   {avg_total:.1f}s")

    # JSON 저장
    report_path = "scripts/manual/batch_test_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)
    print(f"\n  상세 리포트: {report_path}")


if __name__ == "__main__":
    asyncio.run(main())
