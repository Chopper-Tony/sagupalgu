"""
경로: legacy_spikes/secondhand_publisher/publishers/bunjang.py
"""
import logging
import re
from pathlib import Path

from playwright.async_api import Page, TimeoutError as PlaywrightTimeoutError

from ..core.models import ListingPackage, PublishResult, Platform, ProductCondition
from .base import BasePublisher

logger = logging.getLogger(__name__)

CONDITION_MAP = {
    ProductCondition.NEW: "새 상품 (미사용)",
    ProductCondition.LIKE_NEW: "사용감 없음",
    ProductCondition.GOOD: "사용감 적음",
    ProductCondition.FAIR: "사용감 많음",
    ProductCondition.POOR: "고장/파손 상품",
}

CATEGORY_MAP = {
    "스마트폰": ["디지털", "휴대폰", "스마트폰"],
    "휴대폰": ["디지털", "휴대폰", "스마트폰"],
    "아이폰": ["디지털", "휴대폰", "스마트폰"],
    "갤럭시": ["디지털", "휴대폰", "스마트폰"],

    "태블릿": ["디지털", "태블릿"],
    "아이패드": ["디지털", "태블릿"],

    "노트북": ["디지털", "PC/노트북", "노트북/넷북"],
    "맥북": ["디지털", "PC/노트북", "노트북/넷북"],

    "자전거": ["스포츠/레저", "자전거"],
    "여성의류": ["여성의류", "상의"],
    "남성의류": ["남성의류", "상의"],
    "가전제품": ["가전제품", "생활가전"],

    "이어폰": ["디지털", "오디오/영상/관련기기"],
    "헤드폰": ["디지털", "오디오/영상/관련기기"],
    "카메라": ["디지털", "카메라/DSLR"],
    "게임기": ["디지털", "게임/타이틀"],

    "레고": ["키덜트", "레고/블럭"],
    "블록": ["키덜트", "레고/블럭"],
    "블록세트": ["키덜트", "레고/블럭"],
    "레고블럭": ["키덜트", "레고/블럭"],

    "피규어": ["키덜트", "피규어/인형"],
    "의류": ["여성의류", "상의"],
    "신발": ["신발"],
}


class BunjangPublisher(BasePublisher):
    platform = Platform.BUNJANG
    WRITE_URL = "https://m.bunjang.co.kr/products/new"

    def _home_url(self) -> str:
        return "https://m.bunjang.co.kr"

    async def is_logged_in(self, page: Page) -> bool:
        try:
            login_btn = page.locator("a:has-text('로그인'), button:has-text('로그인')")
            return await login_btn.count() == 0
        except Exception:
            return False

    async def login(self, page: Page, phone: str, password: str) -> bool:
        return await self.is_logged_in(page)

    async def _dismiss_banner(self, page: Page):
        selectors = [
            "a:has-text('괜찮아요')",
            "a:has-text('웹에서 볼게요')",
            "button:has-text('괜찮아요')",
            "button:has-text('웹에서 볼게요')",
        ]
        for sel in selectors:
            try:
                el = page.locator(sel).first
                if await el.count() > 0 and await el.is_visible():
                    await el.click()
                    await self._human_delay(500, 800)
                    return
            except Exception:
                continue

    async def _close_image_modal_if_open(self, page: Page):
        """
        이미지 업로드 후 뜨는 미리보기 모달 닫기.
        우상단 X 버튼, ESC, 좌표 클릭 순으로 시도.
        """
        close_selectors = [
            "button[aria-label*='닫기']",
            "button[aria-label*='close']",
            "button:has-text('닫기')",
            "div[role='dialog'] button",
        ]

        for sel in close_selectors:
            try:
                btn = page.locator(sel).last
                if await btn.count() > 0 and await btn.is_visible():
                    await btn.click(force=True)
                    await self._human_delay(500, 1000)
                    return
            except Exception:
                continue

        try:
            await page.keyboard.press("Escape")
            await self._human_delay(500, 800)
        except Exception:
            pass

        try:
            viewport = page.viewport_size
            if viewport:
                await page.mouse.click(viewport["width"] - 35, 60)
                await self._human_delay(500, 800)
        except Exception:
            pass

    async def _get_category_columns(self, page: Page):
        """
        번개장터 카테고리 3열 패널 후보를 찾는다.
        """
        containers = page.locator("ul, div")
        columns = []

        for i in range(await containers.count()):
            try:
                el = containers.nth(i)
                box = await el.bounding_box()
                if not box:
                    continue

                # 카테고리 패널처럼 생긴 세로 컬럼만 고르기
                if box["width"] >= 180 and box["height"] >= 200:
                    text = await el.text_content()
                    if text and (
                        "중분류 선택" in text
                        or "소분류 선택" in text
                        or "디지털" in text
                        or "휴대폰" in text
                        or "스마트폰" in text
                    ):
                        columns.append((box["x"], el))
            except Exception:
                continue

        columns.sort(key=lambda x: x[0])
        return [el for _, el in columns[:3]]

    async def _find_and_click_category_in_column(self, page: Page, text: str, column_index: int) -> bool:
        """
        특정 카테고리 열에서 텍스트를 찾아 클릭
        """
        columns = await self._get_category_columns(page)
        target_column = None

        if len(columns) >= column_index + 1:
            target_column = columns[column_index]
        else:
            target_column = page.locator("body")

        for _ in range(12):
            try:
                exact_text = target_column.locator(f"text='{text}'").first
                if await exact_text.count() > 0 and await exact_text.is_visible():
                    await exact_text.scroll_into_view_if_needed()
                    await exact_text.click(force=True)
                    await self._human_delay(500, 900)
                    logger.info(f"[번개장터] 카테고리 column={column_index} 선택 성공: {text}")
                    return True
            except Exception:
                pass

            try:
                partial = target_column.locator(f"text={text}").first
                if await partial.count() > 0 and await partial.is_visible():
                    await partial.scroll_into_view_if_needed()
                    await partial.click(force=True)
                    await self._human_delay(500, 900)
                    logger.info(f"[번개장터] 카테고리 column={column_index} 부분매칭 선택 성공: {text}")
                    return True
            except Exception:
                pass

            try:
                await target_column.evaluate("(el) => { el.scrollTop = (el.scrollTop || 0) + 220; }")
                await self._human_delay(200, 350)
            except Exception:
                try:
                    await page.mouse.wheel(0, 280)
                    await self._human_delay(200, 350)
                except Exception:
                    pass

        logger.warning(f"[번개장터] 카테고리 column={column_index} 선택 실패: {text}")
        return False

    async def _select_category(self, page: Page, category_str: str):
        """
        번개장터 카테고리 선택
        - 추천 chip 시도
        - 실패 시 3열 패널 직접 선택
        """
        category_str = (category_str or "").strip()

        if category_str in CATEGORY_MAP:
            parts = CATEGORY_MAP[category_str]
        else:
            parts = [p.strip() for p in category_str.split(">") if p.strip()]

        if not parts:
            logger.warning("[번개장터] category_str 비어 있음")
            return

        logger.info(f"[번개장터] 카테고리 입력값: {category_str}, 매핑 결과: {parts}")

        # 1) 추천 chip 직접 클릭
        if len(parts) >= 2:
            chip_text = " > ".join(parts)
            chip_selectors = [
                f"text='{chip_text}'",
                f"button:has-text('{chip_text}')",
                f"span:has-text('{chip_text}')",
            ]
            for sel in chip_selectors:
                try:
                    chip = page.locator(sel).first
                    if await chip.count() > 0 and await chip.is_visible():
                        await chip.click(force=True)
                        await self._human_delay(500, 900)
                        logger.info(f"[번개장터] 추천 카테고리 chip 선택 성공: {chip_text}")
                        return
                except Exception:
                    continue

        # 2) 3열 직접 선택
        success_count = 0
        for idx, part in enumerate(parts[:3]):
            ok = await self._find_and_click_category_in_column(page, part, idx)
            if ok:
                success_count += 1
            else:
                logger.warning(f"[번개장터] 카테고리 '{part}' 선택 실패")

        # 3) 최종 검증
        try:
            selected_locator = page.locator("text=선택한 카테고리").first
            if await selected_locator.count() > 0:
                selected_text = await selected_locator.text_content()
                logger.info(f"[번개장터] 선택한 카테고리 영역: {selected_text}")
        except Exception:
            pass

        if success_count == 0:
            raise Exception(f"번개장터 카테고리 선택 실패: {parts}")

    async def _select_condition(self, page: Page, condition: ProductCondition):
        text = CONDITION_MAP[condition]

        candidates = [
            page.locator(f"label:has-text('{text}')").first,
            page.locator(f"li:has-text('{text}')").first,
            page.locator(f"text='{text}'").first,
        ]

        for target in candidates:
            try:
                if await target.count() > 0 and await target.is_visible():
                    await target.scroll_into_view_if_needed()
                    await target.click(force=True)
                    await self._human_delay()
                    logger.info(f"[번개장터] 상태 선택 성공: {text}")
                    return
            except Exception as e:
                logger.warning(f"[번개장터] 상태 선택 재시도 실패 ({text}): {e}")

        raise Exception(f"번개장터 상품상태 선택 실패: {text}")

    async def _upload_images(self, page: Page, image_paths: list[Path]):
        valid_paths = [str(p) for p in image_paths if p.exists()][:12]
        if not valid_paths:
            logger.warning("[번개장터] 업로드할 이미지 없음")
            return

        file_input = page.locator("input[type='file']").first
        if await file_input.count() > 0:
            await file_input.set_input_files(valid_paths)
            await self._human_delay(2500, 3500)
            logger.info(f"[번개장터] 이미지 {len(valid_paths)}장 업로드")
            return

        raise Exception("번개장터 파일 input[type='file']를 찾지 못함")

    async def _collect_form_errors(self, page: Page) -> str:
        patterns = [
            "10글자 이상",
            "카테고리",
            "상품명",
            "가격",
            "이미지",
            "필수",
        ]

        collected = []
        for pattern in patterns:
            try:
                locator = page.locator(f"text={pattern}")
                count = await locator.count()
                if count > 0:
                    for i in range(min(count, 3)):
                        try:
                            text = await locator.nth(i).text_content()
                            if text:
                                text = text.strip()
                                if text and text not in collected:
                                    collected.append(text)
                        except Exception:
                            continue
            except Exception:
                continue

        return " | ".join(collected)

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

            # ② 이미지 미리보기 모달이 떴으면 닫기
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

            # ⑥ 설명
            desc = page.locator("textarea").first
            if await desc.count() == 0:
                raise Exception("번개장터 설명 textarea를 찾지 못함")

            description = (package.description or "").strip()
            if len(description) < 10:
                description = f"{description} 상태 양호합니다."

            await desc.click()
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

            # 디버깅용: 성공 화면 2분 유지
            await page.wait_for_timeout(120000)

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

            # 디버깅용: 실패 화면 2분 유지
            await page.wait_for_timeout(120000)

            return PublishResult(
                platform=self.platform,
                success=False,
                error_message=str(e),
                screenshot_path=shot,
            )
        finally:
            await page.close()