"""
경로: sagupalgu/test_bunjang_login.py

번개장터 세션 로드 후 글쓰기 페이지 확인
- 사전에 save_sessions.py 실행해서 세션 저장 필요
"""
import asyncio
import os
from playwright.async_api import async_playwright

SESSION_FILE = "sessions/bunjang_session.json"

async def main():
    if not os.path.exists(SESSION_FILE):
        print(f"❌ 세션 파일 없음: {SESSION_FILE}")
        print("먼저 python save_sessions.py 실행해주세요")
        return

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, slow_mo=300)

        # 세션 로드
        context = await browser.new_context(
            storage_state=SESSION_FILE,
            viewport={"width": 1280, "height": 900},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        print("▶ 세션 로드 후 번개장터 이동...")
        await page.goto("https://m.bunjang.co.kr", wait_until="networkidle")
        await asyncio.sleep(2)

        # 앱 배너 닫기
        banner = page.locator("a:has-text('괜찮아요'), a:has-text('웹에서 볼게요')").first
        if await banner.count() > 0:
            await banner.click()
            await asyncio.sleep(1)

        # 로그인 상태 확인
        login_btn = page.locator("a:has-text('로그인'), button:has-text('로그인')").first
        if await login_btn.count() > 0:
            print("❌ 세션 만료 - save_sessions.py 다시 실행 필요")
            await browser.close()
            return
        else:
            print("✅ 로그인 상태 확인!")

        # 판매하기 클릭
        print("▶ 판매하기 클릭...")
        sell_btn = page.locator("a:has-text('판매하기'), button:has-text('판매하기')").first
        if await sell_btn.count() > 0:
            await sell_btn.click()
            await asyncio.sleep(3)
            print(f"✅ 글쓰기 URL: {page.url}")
        else:
            print("❌ 판매하기 버튼 못 찾음")

        # 폼 요소 출력
        print(f"\n=== 현재 페이지: {page.url} ===")
        print("=== 폼 요소 ===")
        elements = await page.locator("input, textarea, select").all()
        for el in elements:
            tag = await el.evaluate("el => el.tagName")
            name = await el.get_attribute("name") or ""
            placeholder = await el.get_attribute("placeholder") or ""
            id_ = await el.get_attribute("id") or ""
            type_ = await el.get_attribute("type") or ""
            print(f"  [{tag}] type={type_} name={name} id={id_} placeholder={placeholder[:40]}")

        await page.screenshot(path="bunjang_write_page.png", full_page=False)
        print("\n✅ 스크린샷 저장: bunjang_write_page.png")
        print("▶ 15초 후 종료...")
        await asyncio.sleep(15)
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())