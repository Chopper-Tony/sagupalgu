import logging
import re
from pathlib import Path

from playwright.async_api import Page, TimeoutError as PlaywrightTimeoutError

from legacy_spikes.secondhand_publisher.publishers.bunjang import (
    BunjangPublisher as LegacyBunjangPublisher,
)
from legacy_spikes.secondhand_publisher.core.models import (
    ListingPackage,
    PublishResult,
    Platform,
)

from app.core.config import settings
from app.publishers.publisher_interface import (
    PlatformPackage,
    PublisherAccountContext,
    PublishResult as AppPublishResult,
    PlatformPublisher,
)
from app.publishers._legacy_utils import to_legacy_listing_package

logger = logging.getLogger(__name__)


class PatchedBunjangPublisher(LegacyBunjangPublisher):
    """
    LegacyBunjangPublisher의 textarea 클릭 버그 수정 버전.
    floating footer가 textarea를 가로막는 문제를 JS focus로 우회.
    """

    async def publish(self, package: ListingPackage) -> PublishResult:
        page = await self.new_page()

        try:
            await page.goto(
                self.WRITE_URL,
                wait_until="domcontentloaded",
                timeout=60000,
            )
            await self._human_delay(1500, 2500)
            await self._dismiss_banner(page)

            if "login" in page.url.lower() or not await self.is_logged_in(page):
                raise Exception("로그인 세션 만료 - save_sessions.py 재실행 필요")

            await page.wait_for_selector(
                "input[placeholder='상품명을 입력해 주세요.']",
                timeout=15000,
            )

            await self.screenshot(page, "write_page")

            # ① 이미지
            await self._upload_images(page, package.image_paths)

            # ② 이미지 미리보기 모달 닫기
            await self._close_image_modal_if_open(page)

            # ③ 상품명
            title_input = page.locator("input[placeholder='상품명을 입력해 주세요.']").first
            await title_input.click()
            await title_input.fill(package.title)
            await self._human_delay()

            # ④ 카테고리
            await self._select_category(page, package.category)

            # ⑤ 상태
            await self._select_condition(page, package.condition)

            # ⑥ 설명 — floating footer 가로막힘 버그 수정: JS focus 사용
            desc = page.locator("textarea").first
            if await desc.count() == 0:
                raise Exception("번개장터 설명 textarea를 찾지 못함")

            description = (package.description or "").strip()
            if len(description) < 10:
                description = f"{description} 상태 양호합니다."

            await desc.scroll_into_view_if_needed()
            await desc.evaluate("(el) => el.focus()")  # click() 대신 JS focus
            await desc.fill(description)
            await self._human_delay()

            # ⑦ 태그
            if package.tags:
                tag_input = page.locator(
                    "input[placeholder='태그를 입력해 주세요. (최대 5개)']"
                ).first
                if await tag_input.count() > 0:
                    for tag in package.tags[:5]:
                        await tag_input.fill(tag)
                        await page.keyboard.press("Space")
                        await self._human_delay(200, 400)

            # ⑧ 가격
            price_input = page.locator("input[placeholder='가격을 입력해 주세요.']").first
            if await price_input.count() == 0:
                raise Exception("번개장터 가격 입력창을 찾지 못함")
            await price_input.click()
            await price_input.fill(str(package.price))
            await self._human_delay()

            # ⑨ 가격제안
            if package.negotiable:
                offer_input = page.locator("#priceOfferEnabled").first
                if await offer_input.count() > 0:
                    try:
                        is_checked = await offer_input.is_checked()
                    except Exception:
                        is_checked = False

                    if not is_checked:
                        offer_label = page.locator(
                            "label[for='priceOfferEnabled'], label:has-text('가격제안')"
                        ).first
                        if await offer_label.count() > 0:
                            await offer_label.click(force=True)
                            await self._human_delay()

            # ⑩ 배송비
            if package.shipping_available:
                shipping = page.locator(
                    "label:has-text('배송비별도'), label:has-text('배송비포함')"
                ).first
                if await shipping.count() > 0:
                    await shipping.click(force=True)
                    await self._human_delay()

            await self.screenshot(page, "before_submit")

            # ⑪ 등록하기
            submit_btn = page.locator("button:has-text('등록하기')").first
            if await submit_btn.count() == 0:
                raise Exception("등록하기 버튼 못 찾음")

            await submit_btn.scroll_into_view_if_needed()
            await submit_btn.click(force=True)
            await self._human_delay(3000, 4500)

            current_url = page.url

            if current_url.rstrip("/") == self.WRITE_URL.rstrip("/"):
                form_errors = await self._collect_form_errors(page)
                if form_errors:
                    raise Exception(f"등록 후에도 번개장터 글쓰기 페이지에 머뭄 - 검증메시지: {form_errors}")
                raise Exception("등록 후에도 여전히 번개장터 글쓰기 페이지에 머뭄")

            try:
                await page.wait_for_url("**/products/**", timeout=10000)
            except PlaywrightTimeoutError:
                pass

            current_url = page.url
            match = re.search(r"/products/(\d+)", current_url)
            if not match:
                raise Exception(f"등록 성공 URL 검증 실패. 현재 URL: {current_url}")

            listing_id = match.group(1)
            shot = await self.screenshot(page, "publish_success")

            await page.wait_for_timeout(30000)

            return PublishResult(
                platform=self.platform,
                success=True,
                listing_url=current_url,
                listing_id=listing_id,
                screenshot_path=shot,
            )

        except Exception as e:
            logger.error(f"[번개장터] publish 실패: {e}")
            shot = await self.screenshot(page, "publish_error")
            await page.wait_for_timeout(30000)
            return PublishResult(
                platform=self.platform,
                success=False,
                error_message=str(e),
                screenshot_path=shot,
            )
        finally:
            await page.close()


class BunjangPublisher(PlatformPublisher):
    async def publish(
        self,
        package: PlatformPackage,
        account: PublisherAccountContext,
    ) -> AppPublishResult:
        legacy_pkg = to_legacy_listing_package(package.payload)

        publisher = PatchedBunjangPublisher(
            headless=settings.publish_headless,
            slow_mo=settings.publish_slow_mo,
        )

        result = await publisher.run(
            package=legacy_pkg,
            phone=account.secret_payload.get("username", ""),
            password=account.secret_payload.get("password", ""),
        )

        return AppPublishResult(
            success=result.success,
            platform="bunjang",
            external_listing_id=result.listing_id,
            external_url=result.listing_url,
            error_message=result.error_message,
            evidence_path=str(result.screenshot_path)
            if result.screenshot_path
            else None,
        )
