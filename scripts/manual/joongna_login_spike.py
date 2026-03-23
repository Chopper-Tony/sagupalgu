"""
경로: sagupalgu/test_joongna_login.py

중고나라 세션 로드 후 글쓰기 페이지 확인
- 사전에 save_sessions.py 실행해서 세션 저장 필요
"""
import asyncio
import os
from playwright.async_api import async_playwright

SESSION_FILE = "sessions/joongna_session.json"

async def main():
    if not os.path.exists(SESSION_FILE):
        print(f"❌ 세션 파일 없음: {SESSION_FILE}")
        print("먼저 python save_sessions.py 실행 → 2 선택")
        return

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, slow_mo=300)
        context = await browser.new_context(
            storage_state=SESSION_FILE,
            viewport={"width": 1280, "height": 900},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        print("▶ 세션 로드 후 중고나라 이동...")
        await page.goto("https://web.joongna.com", wait_until="networkidle")
        await asyncio.sleep(2)

        # 로그인 상태 확인
        login_btn = page.locator("a:has-text('로그인'), button:has-text('로그인')").first
        if await login_btn.count() > 0:
            print("❌ 세션 만료 - save_sessions.py 다시 실행 필요")
            await browser.close()
            return
        print("✅ 로그인 상태 확인!")

        # 판매하기 버튼 클릭
        print("▶ 판매하기 클릭...")
        sell_btn = page.locator("a:has-text('판매하기'), button:has-text('판매하기')").first
        if await sell_btn.count() > 0:
            href = await sell_btn.get_attribute("href") or ""
            print(f"  href: {href}")
            await sell_btn.click()
            await asyncio.sleep(3)
            print(f"  클릭 후 URL: {page.url}")
        else:
            print("  판매하기 버튼 못 찾음 - URL 직접 시도...")
            for url in [
                "https://web.joongna.com/sell",
                "https://web.joongna.com/write",
                "https://web.joongna.com/product/write",
            ]:
                await page.goto(url, wait_until="domcontentloaded")
                await asyncio.sleep(1)
                print(f"  {url} → {page.url}")
                if "write" in page.url or "sell" in page.url:
                    print(f"  ✅ 글쓰기 URL 발견!")
                    break

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

        await page.screenshot(path="joongna_write_page.png", full_page=False)
        print("\n✅ 스크린샷 저장: joongna_write_page.png")
        print("▶ 15초 후 종료...")
        await asyncio.sleep(15)
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())