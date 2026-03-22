import asyncio
import httpx

BASE = "http://127.0.0.1:8000/api/v1"
IMAGE_PATH = "C:/Users/bonjo/Desktop/hahaha.jpg"

async def main():
    async with httpx.AsyncClient(timeout=300) as client:
        # 1. 세션 생성
        r = await client.post(f"{BASE}/sessions")
        session_id = r.json()["session_id"]
        print(f"✅ 세션 생성: {session_id}")

        # 2. 이미지 업로드
        await client.post(f"{BASE}/sessions/{session_id}/images",
            json={"image_urls": [IMAGE_PATH]})
        print("✅ 이미지 업로드")

        # 3. 분석
        r = await client.post(f"{BASE}/sessions/{session_id}/analyze")
        needs_input = r.json().get("needs_user_input", True)
        print(f"✅ 분석 완료 (needs_user_input={needs_input})")

        # 4. 상품 정보 입력
        await client.post(f"{BASE}/sessions/{session_id}/provide-product-info",
            json={"brand": "애플", "model": "아이폰 15 Pro", "category": "스마트폰"})
        print("✅ 상품 정보 입력")

        # 5. 판매글 생성
        await client.post(f"{BASE}/sessions/{session_id}/generate-listing")
        print("✅ 판매글 생성")

        # 6. 게시 준비
        await client.post(f"{BASE}/sessions/{session_id}/prepare-publish",
            json={"platform_targets": ["joongna", "bunjang"]})
        print("✅ 게시 준비")

        # 7. 게시
        r = await client.post(f"{BASE}/sessions/{session_id}/publish")
        print(f"✅ 게시 완료: {r.json()['status']}")
        print(r.json()["publish"])

asyncio.run(main())