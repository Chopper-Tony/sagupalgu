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
        "login_url": "https://m.bunjang.co.kr/login",
        "session_file": "bunjang_session.json",
        "verify_url": "https://m.bunjang.co.kr/my",
        "verify_fail_patterns": ["/login", "/signin"],
    },
    "joongna": {
        "name": "중고나라",
        "login_url": "https://web.joongna.com/signin?type=default",
        "session_file": "joongna_session.json",
        "verify_url": "https://web.joongna.com/my-store",
        "verify_fail_patterns": ["/signin", "/login"],
    },
}


def get_session_status() -> dict[str, Any]:
    """각 플랫폼의 세션 저장 상태를 확인한다."""
    result = {}
    for platform, config in PLATFORM_CONFIG.items():
        path = os.path.join(SESSION_DIR, config["session_file"])
        exists = os.path.exists(path)
        mtime = None
        if exists:
            import datetime
            mtime = datetime.datetime.fromtimestamp(
                os.path.getmtime(path),
                tz=datetime.timezone.utc,
            ).isoformat()
        result[platform] = {
            "name": config["name"],
            "connected": exists,
            "session_saved_at": mtime,
        }
    return result


async def _verify_login(context, config: dict) -> bool:
    """별도 탭을 열어 보호된 페이지 접근으로 로그인 상태를 확인한다.

    로그인 페이지로 리다이렉트되면 미로그인, 아니면 로그인 성공.
    확인 후 탭은 즉시 닫는다.
    """
    check_page = await context.new_page()
    try:
        await check_page.goto(config["verify_url"], wait_until="domcontentloaded", timeout=8000)
        await asyncio.sleep(1)  # 리다이렉트 대기
        final_url = check_page.url
        for pattern in config["verify_fail_patterns"]:
            if pattern in final_url:
                return False
        return True
    except Exception:
        return False
    finally:
        await check_page.close()


async def open_login_browser(platform: str) -> dict[str, Any]:
    """
    Playwright 브라우저를 headless=False로 열어 로그인 페이지를 표시한다.
    사용자가 로그인을 완료하면 자동으로 쿠키를 저장하고 브라우저를 닫는다.

    로그인 감지: 사용자의 로그인 페이지는 건드리지 않고,
    별도 탭에서 보호 페이지 접근을 시도해 리다이렉트 여부로 판단한다.
    """
    if platform not in PLATFORM_CONFIG:
        return {"success": False, "error": f"지원하지 않는 플랫폼: {platform}"}

    config = PLATFORM_CONFIG[platform]

    async def _do_login():
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
            page = await context.new_page()

            # 로그인 페이지 열기
            await page.goto(config["login_url"], wait_until="domcontentloaded")
            await asyncio.sleep(2)

            # 번개장터: 앱 배너 닫기
            if platform == "bunjang":
                banner = page.locator(
                    "a:has-text('괜찮아요'), a:has-text('웹에서 볼게요')"
                ).first
                if await banner.count() > 0:
                    await banner.click()
                    await asyncio.sleep(1)

            logger.info("[%s] 로그인 브라우저 열림 — 사용자 로그인 대기 중 (최대 5분)", config["name"])

            # 첫 10초는 대기 (사용자가 로그인 폼을 보고 입력할 시간)
            await asyncio.sleep(10)

            # 로그인 완료 대기 (최대 5분, 5초 간격 폴링)
            # 별도 탭에서 보호 페이지 접근 → 리다이렉트 여부로 판단
            logged_in = False
            for i in range(55):  # 10초 초기 대기 + 55*5초 = ~5분
                try:
                    if await _verify_login(context, config):
                        logged_in = True
                        logger.info("[%s] 로그인 감지 성공 (폴링 %d회차)", config["name"], i + 1)
                        break
                except Exception:
                    pass
                await asyncio.sleep(5)

            if logged_in:
                os.makedirs(SESSION_DIR, exist_ok=True)
                session_path = os.path.join(SESSION_DIR, config["session_file"])
                await context.storage_state(path=session_path)
                logger.info("[%s] 로그인 성공 — 세션 저장 완료: %s", config["name"], session_path)
                await browser.close()
                return {"success": True, "platform": platform, "name": config["name"]}
            else:
                logger.warning("[%s] 로그인 타임아웃 (5분)", config["name"])
                await browser.close()
                return {"success": False, "error": f"{config['name']} 로그인 시간 초과 (5분)"}

    # Windows에서는 별도 스레드 + ProactorEventLoop 필요
    if sys.platform == "win32":
        import concurrent.futures

        def _run_in_proactor():
            loop = asyncio.ProactorEventLoop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(_do_login())
            finally:
                loop.close()

        loop = asyncio.get_running_loop()
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return await loop.run_in_executor(pool, _run_in_proactor)

    return await _do_login()
