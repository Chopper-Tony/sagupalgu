import asyncio
import os

from playwright.async_api import async_playwright

SESSION_DIR = "sessions"


async def save_bunjang_session():
    print("=" * 50)
    print("번개장터 세션 저장")
    print("=" * 50)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, slow_mo=200)
        context = await browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )
        page = await context.new_page()

        await page.goto("https://m.bunjang.co.kr", wait_until="networkidle")
        await asyncio.sleep(1)

        banner = page.locator("a:has-text('괜찮아요'), a:has-text('웹에서 볼게요')").first
        if await banner.count() > 0:
            await banner.click()
            await asyncio.sleep(1)

        sell_btn = page.locator("a:has-text('판매하기'), button:has-text('판매하기')").first
        if await sell_btn.count() > 0:
            await sell_btn.click()
            await asyncio.sleep(2)

        print("\n브라우저에서 직접 로그인해주세요.")
        print("카카오/네이버 로그인 후 번개장터 메인 화면이 나오면")
        print("이 터미널에서 Enter를 눌러주세요.")
        input(">>> 로그인 완료 후 Enter: ")

        os.makedirs(SESSION_DIR, exist_ok=True)
        await context.storage_state(path=f"{SESSION_DIR}/bunjang_session.json")
        print(f"✅ 세션 저장 완료: {SESSION_DIR}/bunjang_session.json")

        await browser.close()


async def save_joongna_session():
    print("=" * 50)
    print("중고나라 세션 저장")
    print("=" * 50)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, slow_mo=200)
        context = await browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )
        page = await context.new_page()

        await page.goto(
            "https://web.joongna.com/signin?type=default",
            wait_until="domcontentloaded",
        )
        await asyncio.sleep(2)

        print("\n브라우저에서 직접 로그인해주세요.")
        print("네이버로 시작하기 클릭 → 로그인 완료 후")
        print("중고나라 메인 화면이 나오면 Enter를 눌러주세요.")
        input(">>> 로그인 완료 후 Enter: ")

        os.makedirs(SESSION_DIR, exist_ok=True)
        await context.storage_state(path=f"{SESSION_DIR}/joongna_session.json")
        print(f"✅ 세션 저장 완료: {SESSION_DIR}/joongna_session.json")

        await browser.close()


async def main():
    print("어떤 플랫폼 세션을 저장할까요?")
    print("1. 번개장터")
    print("2. 중고나라")
    print("3. 둘 다")
    choice = input("선택 (1/2/3): ").strip()

    if choice == "1":
        await save_bunjang_session()
    elif choice == "2":
        await save_joongna_session()
    elif choice == "3":
        await save_bunjang_session()
        await save_joongna_session()
    else:
        print("잘못된 입력")


if __name__ == "__main__":
    asyncio.run(main())