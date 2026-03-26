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
        "login_page_patterns": ["/login", "/signin"],
        "home_domain": "bunjang.co.kr",
    },
    "joongna": {
        "name": "중고나라",
        "login_url": "https://web.joongna.com/signin?type=default",
        "session_file": "joongna_session.json",
        "login_page_patterns": ["/signin", "/login"],
        "home_domain": "joongna.com",
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


def _is_still_on_login_page(url: str, config: dict) -> bool:
    """현재 URL이 로그인 페이지이거나 OAuth 외부 페이지인지 판단한다.

    로그인 완료 = 해당 플랫폼 도메인에 있으면서 로그인 패턴이 URL에 없는 상태.
    OAuth 페이지(kakao, naver 등)에 있으면 아직 로그인 중.
    """
    # 로그인 페이지 패턴이 URL에 있으면 아직 로그인 중
    for pattern in config["login_page_patterns"]:
        if pattern in url:
            return True
    # 플랫폼 도메인에 있지 않으면 OAuth 외부 페이지 → 아직 로그인 중
    if config["home_domain"] not in url:
        return True
    return False


async def open_login_browser(platform: str) -> dict[str, Any]:
    """
    Playwright 브라우저를 headless=False로 열어 로그인 페이지를 표시한다.
    사용자가 로그인을 완료하면 자동으로 쿠키를 저장하고 브라우저를 닫는다.

    로그인 감지 방식:
    - 로그인 페이지 URL에 login_page_patterns이 포함되어 있으면 "아직 로그인 중"
    - 사용자가 로그인을 완료하면 플랫폼이 다른 페이지로 리다이렉트함
    - URL에서 패턴이 사라지면 로그인 성공으로 판단
    - 페이지를 절대 이동시키지 않음 — 사용자의 로그인 흐름을 방해하지 않음
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

            initial_url = page.url
            logger.info(
                "[%s] 로그인 브라우저 열림 — 사용자 로그인 대기 중 (최대 5분), 초기 URL: %s",
                config["name"], initial_url,
            )

            # 로그인 완료 대기 (최대 5분, 3초 간격 폴링)
            # 판단 기준: 현재 URL에서 login_page_patterns이 모두 사라지면 로그인 성공
            logged_in = False
            for i in range(100):  # 100 * 3초 = 5분
                await asyncio.sleep(3)
                try:
                    current_url = page.url
                    if not _is_still_on_login_page(current_url, config):
                        # URL이 로그인 페이지에서 벗어남 → 로그인 성공
                        logged_in = True
                        logger.info(
                            "[%s] 로그인 감지 (폴링 %d회차), URL: %s",
                            config["name"], i + 1, current_url,
                        )
                        break
                except Exception:
                    # 브라우저가 닫혔거나 페이지 접근 불가
                    pass

            if logged_in:
                # 로그인 후 잠시 대기 (쿠키/세션 안정화)
                await asyncio.sleep(2)
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
