"""
경로: sagupalgu/test_joongna_inspect.py
택배 체크 후 배송비 팝업 HTML 구조 확인 - 사람이 직접 택배 체크
"""
import asyncio
import os
from playwright.async_api import async_playwright

SESSION_FILE = "sessions/joongna_session.json"
WRITE_URL = "https://web.joongna.com/product/form?type=regist"

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, slow_mo=300)
        context = await browser.new_context(
            storage_state=SESSION_FILE,
            viewport={"width": 1280, "height": 900},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        await page.goto(WRITE_URL, wait_until="domcontentloaded")
        await asyncio.sleep(2)

        print("브라우저에서 직접 택배 체크 → 배송비 설정 클릭 → 배송비 포함 선택해주세요")
        print("완료 후 30초 기다리면서 HTML 스캔합니다...")
        await asyncio.sleep(30)

        # 현재 페이지 모든 input/label/button 출력
        print("\n▶ 전체 input/label 요소...")
        els = await page.evaluate('''
            () => {
                const result = [];
                document.querySelectorAll("input, label, button").forEach(el => {
                    const text = el.textContent?.trim().slice(0, 30);
                    if (text || el.id || el.name || el.htmlFor) {
                        result.push({
                            tag: el.tagName,
                            id: el.id || "",
                            name: el.name || "",
                            for: el.htmlFor || "",
                            type: el.type || "",
                            text: text || ""
                        });
                    }
                });
                return result;
            }
        ''')
        for el in els:
            if any(k in str(el).lower() for k in ['parcel', '배송', 'fee', 'ship']):
                print(f"  ★ {el}")
            else:
                print(f"    {el}")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())