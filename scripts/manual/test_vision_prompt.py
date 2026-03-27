"""
M78: Vision AI 프롬프트 실테스트 스크립트.

사용법:
    python scripts/manual/test_vision_prompt.py <이미지경로>
    python scripts/manual/test_vision_prompt.py uploads/089475dc-.../f14c01cf...jpg

실제 OpenAI/Gemini API를 호출하므로 .env에 API 키 필요.
"""
import asyncio
import json
import sys
import os

# 프로젝트 루트를 path에 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from dotenv import load_dotenv
load_dotenv()


async def test_vision(image_path: str):
    from app.vision.openai_provider import OpenAIVisionProvider
    from app.vision.gemini_provider import GeminiVisionProvider
    from app.core.config import settings

    print(f"\n{'='*60}")
    print(f"이미지: {image_path}")
    print(f"{'='*60}")

    if not os.path.exists(image_path):
        print(f"  [ERROR] 파일 없음: {image_path}")
        return

    # OpenAI 테스트
    if settings.openai_api_key:
        print(f"\n--- OpenAI ({settings.openai_vision_model}) ---")
        provider = OpenAIVisionProvider()
        result = await provider.identify_product([image_path])
        _print_result(result)
    else:
        print("\n--- OpenAI: API 키 없음 (skip) ---")

    # Gemini 테스트
    if settings.gemini_api_key:
        print(f"\n--- Gemini ({settings.gemini_vision_model}) ---")
        provider = GeminiVisionProvider()
        result = await provider.identify_product([image_path])
        _print_result(result)
    else:
        print("\n--- Gemini: API 키 없음 (skip) ---")


def _print_result(result):
    print(f"  candidates ({len(result.candidates)}개):")
    for i, c in enumerate(result.candidates):
        brand = c.get("brand", "?")
        model = c.get("model", "?")
        category = c.get("category", "?")
        confidence = c.get("confidence", 0)
        status = "✅" if confidence >= 0.6 else "⚠️"
        print(f"    [{i+1}] {status} {brand} / {model} / {category} (confidence: {confidence})")

    if result.confirmed_hint:
        hint = result.confirmed_hint
        print(f"  confirmed_hint: {hint.get('brand', '?')} / {hint.get('model', '?')} / {hint.get('category', '?')}")

    # shape 검증
    errors = []
    for c in result.candidates:
        for key in ["brand", "model", "category", "confidence"]:
            if key not in c:
                errors.append(f"candidate에 '{key}' 키 없음")
        conf = c.get("confidence", -1)
        if not (0.0 <= conf <= 1.0):
            errors.append(f"confidence 범위 벗어남: {conf}")

    if errors:
        print(f"  [SHAPE ERROR] {errors}")
    else:
        print(f"  [SHAPE OK] 모든 필수 키 존재, confidence 범위 정상")


async def main():
    if len(sys.argv) > 1:
        # 인자로 전달된 이미지
        for path in sys.argv[1:]:
            await test_vision(path)
    else:
        # 기본: uploads에서 첫 5개 세션의 이미지를 테스트
        uploads_dir = "uploads"
        if not os.path.exists(uploads_dir):
            print("uploads/ 디렉터리 없음. 이미지 경로를 인자로 전달하세요.")
            return

        tested = 0
        for session_dir in sorted(os.listdir(uploads_dir))[:10]:
            session_path = os.path.join(uploads_dir, session_dir)
            if not os.path.isdir(session_path):
                continue
            for img_file in os.listdir(session_path):
                if img_file.endswith((".jpg", ".jpeg", ".png")):
                    await test_vision(os.path.join(session_path, img_file))
                    tested += 1
                    break  # 세션당 1개만
            if tested >= 5:
                break

        if tested == 0:
            print("테스트할 이미지를 찾지 못했습니다.")

        print(f"\n{'='*60}")
        print(f"총 {tested}개 이미지 테스트 완료")


if __name__ == "__main__":
    asyncio.run(main())
