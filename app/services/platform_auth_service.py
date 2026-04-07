"""
플랫폼 로그인 세션 관리 서비스.

Playwright 브라우저를 열어 사용자가 직접 로그인하고,
완료 시 쿠키를 서버에 저장한다.
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
from typing import Any

logger = logging.getLogger(__name__)

SESSION_DIR = "sessions"

PLATFORM_CONFIG = {
    "bunjang": {
        "name": "번개장터",
        "login_url": "https://m.bunjang.co.kr",
        "session_file": "bunjang_session.json",
    },
    "joongna": {
        "name": "중고나라",
        "login_url": "https://web.joongna.com/signin?type=default",
        "session_file": "joongna_session.json",
    },
}

# 중고나라 로그인 완료 확인용 HTML (별도 탭에서 표시)
_DONE_PAGE_HTML = """
<!DOCTYPE html>
<html lang="ko">
<head><meta charset="utf-8"><title>로그인 완료 확인</title></head>
<body style="display:flex;align-items:center;justify-content:center;height:100vh;margin:0;
             background:#1a1a2e;color:#fff;font-family:'Noto Sans KR',sans-serif;">
  <div style="text-align:center;">
    <h1 style="font-size:28px;margin-bottom:16px;">🔐 {platform_name}</h1>
    <p style="font-size:16px;color:#aaa;margin-bottom:32px;">
      왼쪽 탭에서 로그인을 완료한 후<br>아래 버튼을 눌러주세요.
    </p>
    <button id="done-btn" style="background:#2563eb;color:#fff;border:none;border-radius:12px;
            padding:16px 48px;font-size:18px;font-weight:700;cursor:pointer;">
      ✅ 로그인 완료
    </button>
    <p id="status" style="margin-top:16px;font-size:14px;color:#666;"></p>
  </div>
  <script>
    document.getElementById('done-btn').addEventListener('click', function() {{
      document.getElementById('status').textContent = '쿠키 저장 중...';
      this.disabled = true;
      window.__LOGIN_DONE__ = true;
    }});
  </script>
</body>
</html>
"""


def _check_session_freshness(session_path: str) -> bool:
    """저장된 세션 파일의 쿠키 만료 여부를 확인한다."""
    try:
        import json
        import time
        with open(session_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        cookies = data.get("cookies", [])
        if not cookies:
            return False
        now = time.time()
        # 만료된 쿠키가 전체의 절반 이상이면 세션 만료로 판정
        expired = sum(1 for c in cookies if c.get("expires", float("inf")) < now)
        return expired < len(cookies) / 2
    except (json.JSONDecodeError, OSError, TypeError):
        return False


def _get_session_path(platform: str, user_id: str | None = None) -> str:
    """세션 파일 경로. user_id가 있으면 user별 분리."""
    config = PLATFORM_CONFIG.get(platform, {})
    filename = config.get("session_file", f"{platform}_session.json")
    if user_id:
        user_dir = os.path.join(SESSION_DIR, user_id)
        os.makedirs(user_dir, exist_ok=True)
        return os.path.join(user_dir, filename)
    return os.path.join(SESSION_DIR, filename)


def get_session_status(user_id: str | None = None) -> dict[str, Any]:
    """각 플랫폼의 세션 저장 상태를 확인한다. 쿠키 만료도 검사."""
    result = {}
    for platform, config in PLATFORM_CONFIG.items():
        # user별 세션 우선, 없으면 공용 세션 확인
        path = _get_session_path(platform, user_id)
        if not os.path.exists(path):
            path = os.path.join(SESSION_DIR, config["session_file"])
        exists = os.path.exists(path)
        mtime = None
        fresh = False
        if exists:
            import datetime
            mtime = datetime.datetime.fromtimestamp(
                os.path.getmtime(path),
                tz=datetime.timezone.utc,
            ).isoformat()
            fresh = _check_session_freshness(path)
        result[platform] = {
            "name": config["name"],
            "connected": exists and fresh,
            "session_saved_at": mtime,
            "session_expired": exists and not fresh,
        }
    return result


def store_platform_session(
    user_id: str,
    platform: str,
    storage_state: dict[str, Any],
) -> str:
    """익스텐션에서 업로드한 세션을 암호화 저장한다."""
    import json
    from app.core.security import encrypt_payload

    path = _get_session_path(platform, user_id)

    # Playwright가 직접 읽을 수 있도록 평문 저장 (세션 디렉토리는 서버 내부)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(storage_state, f, ensure_ascii=False)

    logger.info("platform_session_saved user=%s platform=%s path=%s", user_id, platform, path)
    return path


async def verify_platform_session(
    user_id: str,
    platform: str,
    max_retries: int = 2,
) -> tuple[bool, str]:
    """저장된 세션으로 실제 로그인 상태를 검증한다. (retry 1회 포함)"""
    config = PLATFORM_CONFIG.get(platform)
    if not config:
        return False, "unknown_platform"

    path = _get_session_path(platform, user_id)
    if not os.path.exists(path):
        return False, "session_not_found"

    for attempt in range(max_retries):
        try:
            from playwright.async_api import async_playwright

            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                context = await browser.new_context(storage_state=path)
                page = await context.new_page()

                await page.goto(config["login_url"], wait_until="domcontentloaded", timeout=15000)
                await page.wait_for_timeout(2000)

                url = page.url
                # 로그인 페이지로 리다이렉트되면 실패
                if "login" in url.lower() or "signin" in url.lower():
                    await browser.close()
                    if attempt < max_retries - 1:
                        await asyncio.sleep(3)
                        continue
                    return False, "login_required"

                await browser.close()
                return True, "ok"

        except Exception as e:
            logger.warning("session_verify_failed user=%s platform=%s attempt=%d error=%s",
                          user_id, platform, attempt + 1, e)
            if attempt < max_retries - 1:
                await asyncio.sleep(3)
                continue
            return False, "unknown"

    return False, "unknown"


async def _bunjang_login(config: dict) -> dict[str, Any]:
    """번개장터: 로그인 페이지 + '로그인 완료' 버튼 탭 방식. 2분 대기."""
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, slow_mo=100)
        context = await browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )

        # 탭 1: 로그인 페이지
        login_page = await context.new_page()
        await login_page.goto(config["login_url"], wait_until="domcontentloaded")
        await asyncio.sleep(2)

        # 앱 배너 닫기
        banner = login_page.locator(
            "a:has-text('괜찮아요'), a:has-text('웹에서 볼게요')"
        ).first
        if await banner.count() > 0:
            await banner.click()
            await asyncio.sleep(1)

        # 탭 2: "로그인 완료" 버튼 페이지
        done_page = await context.new_page()
        html = _DONE_PAGE_HTML.format(platform_name=config["name"])
        await done_page.set_content(html)

        # 로그인 탭을 앞으로
        await login_page.bring_to_front()

        logger.info("[번개장터] 로그인 브라우저 열림 — 사용자 로그인 대기 중 (최대 2분)")

        # "로그인 완료" 버튼 클릭 대기 (최대 2분)
        clicked = False
        for _ in range(120):
            await asyncio.sleep(1)
            try:
                result = await done_page.evaluate("() => window.__LOGIN_DONE__ === true")
                if result:
                    clicked = True
                    break
            except Exception as e:
                logger.warning("[번개장터] 로그인 상태 확인 중 오류: %s", e)
                break

        if clicked:
            os.makedirs(SESSION_DIR, exist_ok=True)
            session_path = os.path.join(SESSION_DIR, config["session_file"])
            await context.storage_state(path=session_path)
            logger.info("[번개장터] 로그인 성공 — 세션 저장 완료: %s", session_path)
            await browser.close()
            return {"success": True, "platform": "bunjang", "name": config["name"]}
        else:
            logger.warning("[번개장터] 로그인 타임아웃 (2분) 또는 브라우저 닫힘")
            try:
                await browser.close()
            except Exception as e:
                logger.debug("[번개장터] 브라우저 종료 중 오류 (무시): %s", e)
            return {"success": False, "error": "번개장터 로그인 시간 초과 (2분)"}


async def _joongna_login(config: dict) -> dict[str, Any]:
    """중고나라: 로그인 페이지 + '로그인 완료' 버튼 탭 방식. 2분 대기."""
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, slow_mo=100)
        context = await browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )

        # 탭 1: 로그인 페이지
        login_page = await context.new_page()
        await login_page.goto(config["login_url"], wait_until="domcontentloaded")
        await asyncio.sleep(2)

        # 탭 2: "로그인 완료" 버튼 페이지
        done_page = await context.new_page()
        html = _DONE_PAGE_HTML.format(platform_name=config["name"])
        await done_page.set_content(html)

        # 로그인 탭을 앞으로
        await login_page.bring_to_front()

        logger.info("[중고나라] 로그인 브라우저 열림 — 사용자 로그인 대기 중 (최대 2분)")

        # "로그인 완료" 버튼 클릭 대기 (최대 2분)
        clicked = False
        for _ in range(120):  # 120 * 1초 = 2분
            await asyncio.sleep(1)
            try:
                result = await done_page.evaluate("() => window.__LOGIN_DONE__ === true")
                if result:
                    clicked = True
                    break
            except Exception as e:
                logger.warning("[중고나라] 로그인 상태 확인 중 오류: %s", e)
                break

        if clicked:
            os.makedirs(SESSION_DIR, exist_ok=True)
            session_path = os.path.join(SESSION_DIR, config["session_file"])
            await context.storage_state(path=session_path)
            logger.info("[중고나라] 로그인 성공 — 세션 저장 완료: %s", session_path)
            await browser.close()
            return {"success": True, "platform": "joongna", "name": config["name"]}
        else:
            logger.warning("[중고나라] 로그인 타임아웃 (2분) 또는 브라우저 닫힘")
            try:
                await browser.close()
            except Exception as e:
                logger.debug("[중고나라] 브라우저 종료 중 오류 (무시): %s", e)
            return {"success": False, "error": "중고나라 로그인 시간 초과 (2분)"}


async def open_login_browser(platform: str) -> dict[str, Any]:
    """플랫폼별 로그인 브라우저를 연다."""
    if platform not in PLATFORM_CONFIG:
        return {"success": False, "error": f"지원하지 않는 플랫폼: {platform}"}

    config = PLATFORM_CONFIG[platform]

    if platform == "bunjang":
        coro = _bunjang_login(config)
    else:
        coro = _joongna_login(config)

    # Windows에서는 별도 스레드 + ProactorEventLoop 필요
    if sys.platform == "win32":
        import concurrent.futures

        async def _target():
            return await coro

        def _run_in_proactor():
            loop = asyncio.ProactorEventLoop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(_target())
            finally:
                loop.close()

        running_loop = asyncio.get_running_loop()
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return await running_loop.run_in_executor(pool, _run_in_proactor)

    return await coro
