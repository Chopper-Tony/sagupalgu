"""
경로: legacy_spikes/secondhand_publisher/publishers/joongna.py
"""
import logging
import re
from pathlib import Path

from playwright.async_api import Page

from ..core.models import ListingPackage, PublishResult, Platform, ProductCondition
from .base import BasePublisher

logger = logging.getLogger(__name__)

CONDITION_MAP = {
    ProductCondition.NEW: "새상품",
    ProductCondition.LIKE_NEW: "중고",
    ProductCondition.GOOD: "중고",
    ProductCondition.FAIR: "중고",
    ProductCondition.POOR: "중고",
}


class JoongnaPublisher(BasePublisher):
    platform = Platform.JOONGNA
    WRITE_URL = "https://web.joongna.com/product/form?type=regist"

    def _home_url(self) -> str:
        return "https://web.joongna.com"

    async def is_logged_in(self, page: Page) -> bool:
        try:
            login_link = page.locator("a:has-text('로그인'), button:has-text('로그인')")
            if await login_link.count() > 0:
                return False
            return True
        except Exception:
            return False

    async def login(self, page: Page, phone: str, password: str) -> bool:
        return await self.is_logged_in(page)

    async def _upload_images(self, page: Page, image_paths: list[Path]):
        valid_paths = [str(p) for p in image_paths if p.exists()][:10]
        if not valid_paths:
            raise Exception("중고나라 업로드할 이미지 없음")

        selectors = [
            "input[type='file']",
            "input[accept*='image']",
            "input[multiple][type='file']",
        ]

        for sel in selectors:
            try:
                file_input = page.locator(sel).first
                if await file_input.count() > 0:
                    await file_input.set_input_files(valid_paths)
                    await self._human_delay(1500, 2500)
                    logger.info(f"[중고나라] 이미지 업로드 성공: {sel}")
                    return
            except Exception:
                continue

        raise Exception("중고나라 파일 업로드 input을 찾지 못함")

    async def _select_recommended_category_first(self, page: Page) -> bool:
        """
        중고나라 카테고리 선택 전략:
        - 플랫폼 AI 추천/자동 추천을 우선 그대로 둠
        - 카테고리가 선택되지 않은 경우에만 추천 카테고리 첫 항목 클릭
        """
        await self._human_delay(800, 1400)

        # 카테고리 UI가 렌더링될 때까지 대기
        ready_selectors = [
            "text='추천 카테고리'",
            "div:has-text('추천 카테고리')",
            "text='카테고리'",
        ]

        is_ready = False
        for sel in ready_selectors:
            try:
                loc = page.locator(sel).first
                if await loc.count() > 0:
                    await loc.wait_for(state="visible", timeout=5000)
                    is_ready = True
                    break
            except Exception:
                continue

        if not is_ready:
            logger.warning("[중고나라] 추천 카테고리 영역이 보이지 않음")
            return False

        fallback_locators = [
            page.locator("text='추천 카테고리'").locator("xpath=following::button[1]"),
            page.locator("text='추천 카테고리'").locator("xpath=following::*[@role='button'][1]"),
            page.locator("text='추천 카테고리'").locator("xpath=following::div[1]"),
            page.locator("div:has-text('추천 카테고리') button").first,
            page.locator("div:has-text('추천 카테고리') [role='button']").first,
        ]

        for idx, loc in enumerate(fallback_locators, start=1):
            try:
                if await loc.count() > 0:
                    await loc.scroll_into_view_if_needed()
                    await loc.click(force=True)
                    logger.info(f"[중고나라] 추천 카테고리 첫 항목 클릭 성공 (fallback #{idx})")
                    await self._human_delay(800, 1400)
                    return True
            except Exception:
                continue

        logger.warning("[중고나라] 추천 카테고리 첫 항목 클릭 실패")
        return False

    async def publish(self, package: ListingPackage) -> PublishResult:
        page = await self.new_page()

        try:
            await page.goto(
                self.WRITE_URL,
                wait_until="domcontentloaded",
                timeout=60000,
            )
            await self._human_delay(1200, 2200)

            if "login" in page.url.lower():
                raise Exception("로그인 세션 만료")

            title_sel = "input[placeholder*='상품명']"
            await page.wait_for_selector(title_sel, timeout=15000)

            await self.screenshot(page, "write_page")

            # ① 이미지
            await self._upload_images(page, package.image_paths)

            # ② 상품명
            await self._safe_fill(page, title_sel, package.title)
            await self._human_delay(1200, 2000)

            # ③ 카테고리
            category_selected = await self._select_recommended_category_first(page)
            if not category_selected:
                logger.warning("[중고나라] 카테고리 fallback 선택 실패 - 이후 등록 실패 가능성 높음")
            await self._human_delay(1200, 2000)

            # ④ 가격
            price_sel = "input[placeholder*='판매가격'], input[placeholder*='가격']"
            await self._safe_fill(page, price_sel, str(package.price))
            await self._human_delay()

            # ⑤ 설명
            desc_sel = "textarea"
            desc = page.locator(desc_sel).first
            if await desc.count() > 0:
                await desc.click()
                await desc.fill(package.description)
                await self._human_delay()
            else:
                logger.warning("[중고나라] 설명 입력창을 찾지 못함")

            # ⑥ 상태
            condition_text = CONDITION_MAP.get(package.condition, "중고")
            cond = page.locator(f"text='{condition_text}'").first
            if await cond.count() > 0:
                try:
                    await cond.click(force=True)
                    await self._human_delay()
                except Exception:
                    logger.warning(f"[중고나라] 상태 '{condition_text}' 선택 실패")
            else:
                logger.warning(f"[중고나라] 상태 '{condition_text}' 선택 실패")

            # ⑦ 배송 거래
            if package.shipping_available:
                delivery_candidates = [
                    "text='택배거래'",
                    "text='배송비 포함'",
                    "text='배송비 별도'",
                ]
                for sel in delivery_candidates:
                    try:
                        delivery = page.locator(sel).first
                        if await delivery.count() > 0:
                            await delivery.click(force=True)
                            await self._human_delay()
                            break
                    except Exception:
                        continue

            await self.screenshot(page, "before_submit")

            # ⑧ 판매하기
            submit_btn = page.locator("button:has-text('판매하기')").first
            if await submit_btn.count() == 0:
                raise Exception("중고나라 판매하기 버튼을 찾지 못함")

            await submit_btn.scroll_into_view_if_needed()
            await submit_btn.click(force=True)
            await self._human_delay(3000, 4500)

            current_url = page.url

            # 성공 검증
            if "form?type=regist" in current_url:
                raise Exception("등록 후에도 중고나라 글쓰기 폼에 머뭄")

            match = re.search(r"/(\d+)(?:\?|$)", current_url)

            try:
                shot = await self.screenshot(page, "publish_success")
            except Exception:
                shot = None

            # 디버깅용: 성공 화면 30초 유지
            try:
                await page.wait_for_timeout(30000)
            except Exception:
                pass

            return PublishResult(
                platform=self.platform,
                success=True,
                listing_url=current_url,
                listing_id=match.group(1) if match else None,
                screenshot_path=shot,
            )

        except Exception as e:
            logger.error(f"[중고나라] publish 실패: {e}")

            try:
                shot = await self.screenshot(page, "publish_error")
            except Exception:
                shot = None

            # 디버깅용: 실패 화면 30초 유지
            try:
                await page.wait_for_timeout(30000)
            except Exception:
                pass

            return PublishResult(
                platform=self.platform,
                success=False,
                error_message=str(e),
                screenshot_path=shot,
            )
        finally:
            try:
                await page.close()
            except Exception:
                pass