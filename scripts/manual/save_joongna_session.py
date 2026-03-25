"""중고나라 로그인 세션 저장. 브라우저가 뜨면 수동 로그인 후 Enter."""
import asyncio
from playwright.async_api import async_playwright


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()
        await page.goto("https://web.joongna.com")
        print("\n=== 중고나라에 로그인하세요 ===")
        print("로그인 완료되면 이 터미널에서 Enter를 누르세요.\n")
        input(">>> Enter 입력 대기 중...")
        await context.storage_state(path="joongna_session.json")
        print("세션 저장 완료: joongna_session.json")
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
