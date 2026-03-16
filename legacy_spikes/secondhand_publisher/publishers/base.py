"""
Publisher 베이스 클래스
모든 플랫폼 Publisher가 상속
"""
import asyncio
import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

from playwright.async_api import async_playwright, Browser, BrowserContext, Page, Playwright

from ..core.models import ListingPackage, PublishResult, Platform

logger = logging.getLogger(__name__)


class BasePublisher(ABC):
    """
    웹 플랫폼 Publisher 베이스 클래스
    - Playwright 브라우저 자동화
    - 세션(로그인 상태) 저장/재사용
    - 스크린샷 기반 오류 추적
    """

    def __init__(
        self,
        session_dir: Path = Path("./sessions"),
        screenshot_dir: Path = Path("./screenshots"),
        headless: bool = True,
        slow_mo: int = 100,   # ms 딜레이 (사람처럼 보이게)
    ):
        self.session_dir = session_dir
        self.screenshot_dir = screenshot_dir
        self.headless = headless
        self.slow_mo = slow_mo

        self.session_dir.mkdir(parents=True, exist_ok=True)
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)

        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None

    @property
    @abstractmethod
    def platform(self) -> Platform:
        pass

    @property
    def session_file(self) -> Path:
        return self.session_dir / f"{self.platform.name.lower()}_session.json"

    # ─────────────────────────────────────────
    # 브라우저 라이프사이클
    # ─────────────────────────────────────────

    async def _launch(self):
        """브라우저 + 컨텍스트 초기화 (세션 복원 시도)"""
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=self.headless,
            slow_mo=self.slow_mo,
            args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",  # 봇 감지 우회
            ],
        )

        context_options = {
            "viewport": {"width": 1280, "height": 900},
            "user_agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
            "locale": "ko-KR",
            "timezone_id": "Asia/Seoul",
        }

        # 저장된 세션(쿠키/localStorage) 복원
        if self.session_file.exists():
            context_options["storage_state"] = str(self.session_file)
            logger.info(f"[{self.platform.value}] 저장된 세션 복원")

        self._context = await self._browser.new_context(**context_options)

        # 자동화 감지 방지 스크립트
        await self._context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            Object.defineProperty(navigator, 'plugins', { get: () => [1,2,3] });
        """)

    async def _close(self):
        """브라우저 종료 + 세션 저장"""
        if self._context:
            await self._context.storage_state(path=str(self.session_file))
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        logger.info(f"[{self.platform.value}] 브라우저 종료, 세션 저장 완료")

    async def new_page(self) -> Page:
        return await self._context.new_page()

    # ─────────────────────────────────────────
    # 유틸리티
    # ─────────────────────────────────────────

    async def screenshot(self, page: Page, name: str) -> Path:
        path = self.screenshot_dir / f"{self.platform.name.lower()}_{name}.png"
        await page.screenshot(path=str(path), full_page=False)
        return path

    async def _human_delay(self, min_ms: int = 300, max_ms: int = 800):
        """사람처럼 랜덤 딜레이"""
        import random
        await asyncio.sleep(random.randint(min_ms, max_ms) / 1000)

    async def _safe_fill(self, page: Page, selector: str, text: str, delay: int = 50):
        """한 글자씩 타이핑 (봇 감지 우회)"""
        await page.locator(selector).click()
        await page.locator(selector).fill("")
        await page.locator(selector).type(text, delay=delay)

    # ─────────────────────────────────────────
    # 추상 메서드 (각 플랫폼이 구현)
    # ─────────────────────────────────────────

    @abstractmethod
    async def is_logged_in(self, page: Page) -> bool:
        """현재 로그인 상태 여부 확인"""
        pass

    @abstractmethod
    async def login(self, page: Page, phone: str, password: str) -> bool:
        """로그인 수행"""
        pass

    @abstractmethod
    async def publish(self, package: ListingPackage) -> PublishResult:
        """게시글 작성 및 등록"""
        pass

    # ─────────────────────────────────────────
    # 메인 엔트리포인트
    # ─────────────────────────────────────────

    async def run(
        self,
        package: ListingPackage,
        phone: str,
        password: str,
    ) -> PublishResult:
        """
        전체 흐름:
        브라우저 시작 → 로그인 확인 → (필요시 로그인) → 게시 → 종료
        """
        await self._launch()
        page = await self.new_page()

        try:
            # 1. 로그인 상태 확인
            home_url = self._home_url()
            await page.goto(home_url, wait_until="domcontentloaded")
            await self._human_delay(500, 1000)

            if not await self.is_logged_in(page):
                logger.info(f"[{self.platform.value}] 로그인 필요")
                login_ok = await self.login(page, phone, password)
                if not login_ok:
                    return PublishResult(
                        platform=self.platform,
                        success=False,
                        error_message="로그인 실패",
                        screenshot_path=await self.screenshot(page, "login_failed"),
                    )
                logger.info(f"[{self.platform.value}] 로그인 성공")

            # 2. 게시
            result = await self.publish(package.for_platform(self.platform))
            return result

        except Exception as e:
            logger.exception(f"[{self.platform.value}] 오류 발생")
            shot = await self.screenshot(page, "error")
            return PublishResult(
                platform=self.platform,
                success=False,
                error_message=str(e),
                screenshot_path=shot,
            )
        finally:
            await self._close()

    @abstractmethod
    def _home_url(self) -> str:
        pass
