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

CATEGORY_MAP = {
    "스마트폰": ["모바일/태블릿", "휴대폰/스마트폰"],
    "노트북": ["노트북/PC"],
    "태블릿": ["모바일/태블릿", "태블릿"],
    "카메라": ["카메라/캠코더"],
    "블록세트": ["출산/유아동", "유아동교구/완구", "블록/레고"],
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
                    return
            except Exception:
                continue

        raise Exception("중고나라 파일 업로드 input을 찾지 못함")

    async def _select_category(self, page: Page, category_str: str):
        """
        중고나라 카테고리 3단 선택
        """
        category_str = (category_str or "").strip()

        if category_str in CATEGORY_MAP:
            parts = CATEGORY_MAP[category_str]
        else:
            parts = [p.strip() for p in category_str.split(">") if p.strip()]

        if not parts:
            logger.warning("[중고나라] 카테고리 정보 없음")
            return

        for part in parts:
            item = page.locator(
                f"text='{part}', button:has-text('{part}'), div:has-text('{part}')"
            ).first
            if await item.count() > 0:
                await item.scroll_into_view_if_needed()
                await item.click()
                await self._human_delay(500, 900)
            else:
                logger.warning(f"[중고나라] 카테고리 '{part}' 선택 실패")

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
            await self._human_delay()

            # ③ 카테고리
            await self._select_category(page, package.category)

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
                await cond.click()
                await self._human_delay()
            else:
                logger.warning(f"[중고나라] 상태 '{condition_text}' 선택 실패")

            # ⑦ 배송 거래
            if package.shipping_available:
                delivery = page.locator("text='택배거래', text='배송비 포함', text='배송비 별도'").first
                if await delivery.count() > 0:
                    await delivery.click()
                    await self._human_delay()

            await self.screenshot(page, "before_submit")

            # ⑧ 판매하기
            submit_btn = page.locator("button:has-text('판매하기')").first
            if await submit_btn.count() == 0:
                raise Exception("중고나라 판매하기 버튼을 찾지 못함")

            await submit_btn.scroll_into_view_if_needed()
            await submit_btn.click()
            await self._human_delay(3000, 4500)

            current_url = page.url

            # 성공 검증 강화
            if "form?type=regist" in current_url:
                # 아직 폼에 머물면 실패
                raise Exception("등록 후에도 중고나라 글쓰기 폼에 머뭄")

            match = re.search(r"/(\d+)(?:\?|$)", current_url)
            shot = await self.screenshot(page, "publish_success")

            return PublishResult(
                platform=self.platform,
                success=True,
                listing_url=current_url,
                listing_id=match.group(1) if match else None,
                screenshot_path=shot,
            )

        except Exception as e:
            logger.error(f"[중고나라] publish 실패: {e}")
            shot = await self.screenshot(page, "publish_error")
            return PublishResult(
                platform=self.platform,
                success=False,
                error_message=str(e),
                screenshot_path=shot,
            )
        finally:
            await page.close()