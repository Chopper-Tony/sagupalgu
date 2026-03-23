"""
중고나라 게시 테스트
- 세션 파일: sessions/joongna_session.json
- 거래방식: 택배 + 배송비 포함
"""
import asyncio
import os
from playwright.async_api import async_playwright

SESSION_FILE = "sessions/joongna_session.json"
WRITE_URL = "https://web.joongna.com/product/form?type=regist"

async def js_click(page, element_id):
    """React 상태 변경을 위한 JS 클릭"""
    await page.evaluate(f'''
        var el = document.getElementById("{element_id}");
        if (el) {{
            el.focus();
            el.click();
            el.dispatchEvent(new MouseEvent("click", {{bubbles: true}}));
            el.dispatchEvent(new Event("change", {{bubbles: true}}));
        }}
    ''')

async def main():
    if not os.path.exists(SESSION_FILE):
        print(f"❌ 세션 파일 없음: {SESSION_FILE}")
        return

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, slow_mo=400)
        context = await browser.new_context(
            storage_state=SESSION_FILE,
            viewport={"width": 1280, "height": 900},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        print("▶ 글쓰기 페이지 이동...")
        await page.goto(WRITE_URL, wait_until="domcontentloaded")
        await asyncio.sleep(3)

        # ① 이미지 업로드
        print("▶ 이미지 업로드...")
        import pathlib
        img_path = str(pathlib.Path("test_image.jpg").resolve())
        await page.locator("input[name='media']").set_input_files(img_path)
        await asyncio.sleep(2)
        print("  ✅ 이미지 업로드 완료")

        # ② 상품명
        print("▶ 상품명 입력...")
        await page.click("input[name='productTitle']")
        await page.fill("input[name='productTitle']", "테스트 상품 (바로 삭제 예정)")
        await asyncio.sleep(0.5)

        # ② 카테고리 (3단계: 모바일/태블릿 → 스마트폰 → 삼성)
        print("▶ 카테고리 선택...")
        await page.locator("button:has-text('모바일/태블릿')").first.click()
        await asyncio.sleep(1)
        await page.locator("button:has-text('스마트폰')").first.click()
        await asyncio.sleep(1)
        await page.locator("button:has-text('삼성')").first.click()
        await asyncio.sleep(1)

        # ③ 가격
        print("▶ 가격 입력...")
        await page.click("input[name='productPrice']")
        await page.fill("input[name='productPrice']", "10000")
        await asyncio.sleep(0.5)

        # ④ 상품 설명
        print("▶ 상품 설명 입력...")
        await page.click("textarea[name='productDescription']")
        await page.fill("textarea[name='productDescription']", "자동화 테스트용입니다. 즉시 삭제합니다.")
        await asyncio.sleep(0.5)

        # ⑤ 상품 상태 (중고)
        print("▶ 상품 상태 선택...")
        await js_click(page, "used")
        await asyncio.sleep(0.5)

        # ⑥ 구성품 없음
        print("▶ 구성품 선택...")
        await js_click(page, "none")
        await asyncio.sleep(0.5)

        # ⑦ 직거래/픽업 해제
        print("▶ 직거래/픽업 해제...")
        is_meet = await page.evaluate('document.getElementById("isMeet").checked')
        if is_meet:
            await js_click(page, "isMeet")
            await asyncio.sleep(0.3)
            print("  직거래 해제")
        is_pickup = await page.evaluate('document.getElementById("isPickup").checked')
        if is_pickup:
            await js_click(page, "isPickup")
            await asyncio.sleep(0.3)
            print("  픽업 해제")

        # ⑧ 택배 체크
        print("▶ 택배 체크...")
        is_post = await page.evaluate('document.getElementById("isPost").checked')
        if not is_post:
            await js_click(page, "isPost")
            await asyncio.sleep(1)
        is_post2 = await page.evaluate('document.getElementById("isPost").checked')
        print(f"  택배 체크 상태: {is_post2}")

        # ⑨ 배송비 포함 - DOM에 항상 있음, JS로 강제 클릭
        print("▶ 배송비 포함 선택...")
        await asyncio.sleep(0.5)
        await js_click(page, "parcelFeeY")
        await asyncio.sleep(0.5)
        is_parcel = await page.evaluate('document.getElementById("parcelFeeY").checked')
        print(f"  배송비 포함 상태: {is_parcel}")

        await page.screenshot(path="joongna_before_submit.png", full_page=False)
        print("✅ 스크린샷 저장: joongna_before_submit.png")

        # ⑩ 판매하기
        print("▶ 판매하기 클릭...")
        submit_btn = page.locator("button:has-text('판매하기')").last
        if await submit_btn.count() > 0:
            await submit_btn.click()
            await asyncio.sleep(3)
            print(f"  클릭 후 URL: {page.url}")
        else:
            print("  ❌ 판매하기 버튼 못 찾음")

        print(f"\n{'='*40}")
        if page.url != WRITE_URL:
            print(f"✅ 게시 성공! URL: {page.url}")
            print("⚠️  테스트 게시글이므로 직접 삭제해주세요!")
        else:
            print("❌ URL 그대로 - 등록 실패")
            await page.screenshot(path="joongna_error.png")
            print("   joongna_error.png 확인해주세요")

        print("▶ 15초 후 종료...")
        await asyncio.sleep(15)
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())