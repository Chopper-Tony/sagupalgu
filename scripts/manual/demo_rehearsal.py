"""
M82: 데모 리허설 스크립트.

전체 파이프라인을 순서대로 실행하며 각 단계 소요시간/성공여부를 리포트.
실패 시 어디서 멈췄는지 즉시 확인 가능.

사용법:
    # 서버 실행 후
    uvicorn app.main:app --reload

    # 기본 실행 (uploads에서 이미지 자동 탐색)
    python scripts/manual/demo_rehearsal.py

    # 이미지 지정
    python scripts/manual/demo_rehearsal.py --image path/to/image.jpg

    # 게시 없이 게시 준비까지만
    python scripts/manual/demo_rehearsal.py --skip-publish

    # golden session 저장
    python scripts/manual/demo_rehearsal.py --save-golden
"""
import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

BASE = "http://127.0.0.1:8000/api/v1"
GOLDEN_DIR = "scripts/manual/golden_sessions"


class StepResult:
    def __init__(self, name: str):
        self.name = name
        self.success = False
        self.elapsed = 0.0
        self.error = ""
        self.data = {}
        self._start = 0.0

    def start(self):
        self._start = time.time()
        print(f"\n{'─'*50}")
        print(f"▶ {self.name}...")

    def ok(self, data=None, msg=""):
        self.elapsed = time.time() - self._start
        self.success = True
        self.data = data or {}
        extra = f" — {msg}" if msg else ""
        print(f"  ✅ 성공 ({self.elapsed:.1f}초){extra}")

    def fail(self, error: str):
        self.elapsed = time.time() - self._start
        self.error = error
        print(f"  ❌ 실패 ({self.elapsed:.1f}초): {error}")


async def run_rehearsal(image_path: str, skip_publish: bool, save_golden: bool):
    import httpx

    steps: list[StepResult] = []
    session_id = ""

    async with httpx.AsyncClient(timeout=300) as client:

        # ── 0. 헬스체크 ─────────────────────────────
        step = StepResult("헬스체크")
        step.start()
        steps.append(step)
        try:
            r = await client.get(f"{BASE.replace('/api/v1', '')}/health/ready")
            health = r.json()
            if r.status_code == 200:
                step.ok(health, f"status={health.get('status')}")
            else:
                step.fail(f"HTTP {r.status_code}: {health}")
                return steps
        except Exception as e:
            step.fail(f"서버 연결 실패: {e}")
            return steps

        # ── 1. 세션 생성 ─────────────────────────────
        step = StepResult("세션 생성")
        step.start()
        steps.append(step)
        try:
            r = await client.post(f"{BASE}/sessions")
            r.raise_for_status()
            session_id = r.json()["session_id"]
            step.ok(r.json(), f"session_id={session_id[:8]}...")
        except Exception as e:
            step.fail(str(e))
            return steps

        # ── 2. 이미지 업로드 ─────────────────────────
        step = StepResult("이미지 업로드")
        step.start()
        steps.append(step)
        try:
            with open(image_path, "rb") as f:
                files = {"files": (Path(image_path).name, f, "image/jpeg")}
                r = await client.post(f"{BASE}/sessions/{session_id}/images", files=files)
            r.raise_for_status()
            data = r.json()
            img_count = len(data.get("image_urls", []))
            step.ok(data, f"이미지 {img_count}개")
        except Exception as e:
            step.fail(str(e))
            return steps

        # ── 3. 상품 분석 (Vision AI) ─────────────────
        step = StepResult("상품 분석 (Vision AI)")
        step.start()
        steps.append(step)
        try:
            r = await client.post(f"{BASE}/sessions/{session_id}/analyze")
            r.raise_for_status()
            data = r.json()
            candidates = data.get("product_candidates", [])
            needs_input = data.get("needs_user_input", True)
            if candidates:
                top = candidates[0]
                step.ok(data, f"{top.get('brand','?')}/{top.get('model','?')} (confidence={top.get('confidence',0)})")
            else:
                step.ok(data, f"needs_user_input={needs_input}")
        except Exception as e:
            step.fail(str(e))
            return steps

        # ── 4. 상품 확정 ─────────────────────────────
        step = StepResult("상품 확정")
        step.start()
        steps.append(step)
        try:
            data = r.json()
            candidates = data.get("product_candidates", [])
            if candidates and candidates[0].get("confidence", 0) >= 0.6:
                # Vision 결과 신뢰 → 자동 확정
                r = await client.post(f"{BASE}/sessions/{session_id}/confirm-product",
                                      json={"candidate_index": 0})
            else:
                # 신뢰 부족 → 직접 입력
                r = await client.post(f"{BASE}/sessions/{session_id}/provide-product-info",
                                      json={"brand": "테스트", "model": "테스트 상품", "category": "기타"})
            r.raise_for_status()
            confirmed = r.json().get("confirmed_product", {})
            step.ok(r.json(), f"{confirmed.get('brand','?')}/{confirmed.get('model','?')}")
        except Exception as e:
            step.fail(str(e))
            return steps

        # ── 5. 판매글 생성 ───────────────────────────
        step = StepResult("판매글 생성 (LLM + Critic)")
        step.start()
        steps.append(step)
        try:
            r = await client.post(f"{BASE}/sessions/{session_id}/generate-listing")
            r.raise_for_status()
            data = r.json()
            listing = data.get("canonical_listing", {})
            title = listing.get("title", "?")
            price = listing.get("price", 0)
            step.ok(data, f"'{title[:30]}...' / {price:,}원")
        except Exception as e:
            step.fail(str(e))
            return steps

        # ── 6. 게시 준비 ────────────────────────────
        step = StepResult("게시 준비")
        step.start()
        steps.append(step)
        try:
            r = await client.post(f"{BASE}/sessions/{session_id}/prepare-publish",
                                  json={"platform_targets": ["joongna"]})
            r.raise_for_status()
            platforms = r.json().get("selected_platforms", [])
            step.ok(r.json(), f"플랫폼: {platforms}")
        except Exception as e:
            step.fail(str(e))
            return steps

        if skip_publish:
            print(f"\n{'─'*50}")
            print("⏭  --skip-publish: 게시 실행 건너뜀")
        else:
            # ── 7. 게시 실행 ────────────────────────
            step = StepResult("게시 실행")
            step.start()
            steps.append(step)
            try:
                r = await client.post(f"{BASE}/sessions/{session_id}/publish")
                r.raise_for_status()
                data = r.json()
                results = data.get("platform_results", [])
                for pr in results:
                    platform = pr.get("platform", "?")
                    success = pr.get("success", False)
                    url = pr.get("listing_url", "")
                    status = "✅" if success else "❌"
                    print(f"    {status} {platform}: {url or pr.get('error_message', '')}")
                any_success = any(pr.get("success") for pr in results)
                step.ok(data, f"{'성공' if any_success else '실패'}")
            except Exception as e:
                step.fail(str(e))

    # ── golden session 저장 ──────────────────────
    if save_golden and session_id:
        os.makedirs(GOLDEN_DIR, exist_ok=True)
        golden_path = os.path.join(GOLDEN_DIR, f"{session_id[:8]}.json")
        golden_data = {
            "session_id": session_id,
            "image_path": image_path,
            "steps": [
                {"name": s.name, "success": s.success, "elapsed": round(s.elapsed, 1), "error": s.error}
                for s in steps
            ],
        }
        with open(golden_path, "w", encoding="utf-8") as f:
            json.dump(golden_data, f, ensure_ascii=False, indent=2)
        print(f"\n💾 Golden session 저장: {golden_path}")

    # ── 리포트 ───────────────────────────────────
    print(f"\n{'═'*50}")
    print("📊 데모 리허설 결과")
    print(f"{'═'*50}")

    total_time = sum(s.elapsed for s in steps)
    passed = sum(1 for s in steps if s.success)
    failed = sum(1 for s in steps if not s.success)

    for s in steps:
        icon = "✅" if s.success else "❌"
        print(f"  {icon} {s.name:<30} {s.elapsed:>6.1f}초  {s.error}")

    print(f"{'─'*50}")
    print(f"  총 소요시간: {total_time:.1f}초")
    print(f"  성공: {passed} / 실패: {failed} / 전체: {len(steps)}")

    if failed > 0:
        print(f"\n⚠️  실패한 단계가 있습니다. 데모 전 수정이 필요합니다.")
    else:
        print(f"\n🎉 모든 단계 성공! 데모 준비 완료.")

    return steps


def find_test_image() -> str:
    """uploads에서 사용 가능한 이미지를 자동 탐색."""
    uploads = Path("uploads")
    if uploads.exists():
        for session_dir in sorted(uploads.iterdir()):
            if not session_dir.is_dir():
                continue
            for img in session_dir.iterdir():
                if img.suffix.lower() in (".jpg", ".jpeg", ".png"):
                    return str(img)
    # fallback
    if Path("test_image.jpg").exists():
        return "test_image.jpg"
    return ""


def main():
    parser = argparse.ArgumentParser(description="데모 리허설 스크립트")
    parser.add_argument("--image", help="테스트 이미지 경로")
    parser.add_argument("--skip-publish", action="store_true", help="게시 실행 건너뛰기")
    parser.add_argument("--save-golden", action="store_true", help="golden session 저장")
    args = parser.parse_args()

    image_path = args.image or find_test_image()
    if not image_path or not os.path.exists(image_path):
        print(f"❌ 테스트 이미지를 찾을 수 없습니다: {image_path}")
        print("   --image 옵션으로 이미지 경로를 지정하세요.")
        sys.exit(1)

    print(f"🎬 데모 리허설 시작")
    print(f"   이미지: {image_path}")
    print(f"   서버: {BASE}")
    print(f"   게시: {'건너뜀' if args.skip_publish else '실행'}")

    asyncio.run(run_rehearsal(image_path, args.skip_publish, args.save_golden))


if __name__ == "__main__":
    main()
