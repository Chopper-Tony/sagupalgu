"""
Gemini Vision Provider — Google Gemini API 기반 상품 식별.

사용법:
  .env에 GEMINI_API_KEY 설정 + VISION_PROVIDER=gemini
"""
import base64
import json
import logging
import mimetypes
import re
from pathlib import Path

from app.core.config import settings
from app.vision.vision_provider import ProductIdentityResult, VisionProvider

logger = logging.getLogger(__name__)

PROMPT = '''
You are a Korean secondhand marketplace product identification expert.
Given one or more product photos, carefully examine visual details (logos, text, shape, material, accessories) to identify the exact product.

IMPORTANT RULES:
- Identify ONLY what you actually see in the photos. Do NOT guess or default to popular products like smartphones.
- If you cannot identify the exact brand/model, describe what you see (e.g. "만년필", "기계식 키보드", "가죽 가방").
- confidence should reflect how certain you are: 0.9+ only if brand/model text is clearly visible.
- Respond with Korean category names when possible.

Common categories (not limited to):
전자기기, 스마트폰, 노트북, 태블릿, 이어폰/헤드폰, 스피커, 카메라, 게임기,
의류, 신발, 가방, 시계, 액세서리, 쥬얼리,
가구, 가전, 주방용품, 생활용품,
도서, 음반, 문구/필기구, 악기,
스포츠용품, 자전거, 캠핑용품,
유아용품, 반려동물용품, 식품, 기타

Return STRICT JSON only (no markdown, no explanation):
{
  "candidates": [
    {
      "brand": "브랜드명 (모르면 빈 문자열)",
      "model": "모델명 (모르면 사진에서 보이는 제품 설명)",
      "category": "카테고리",
      "confidence": 0.0
    }
  ],
  "confirmed_hint": {
    "brand": "string",
    "model": "string",
    "category": "string",
    "storage": "string or empty",
    "color": "string or empty",
    "condition": "string or empty",
    "bundle": []
  }
}
'''


def _extract_json(text: str) -> dict:
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", text)
        if not match:
            raise
        return json.loads(match.group(0))


class GeminiVisionProvider(VisionProvider):
    async def identify_product(self, images: list[str]) -> ProductIdentityResult:
        if not settings.gemini_api_key:
            logger.warning("GEMINI_API_KEY 미설정")
            return ProductIdentityResult(
                candidates=[{
                    "brand": "Unknown",
                    "model": "Unknown",
                    "category": "unknown",
                    "confidence": 0.1,
                }],
                confirmed_hint=None,
                raw_response={"provider": "gemini", "mock": True, "reason": "GEMINI_API_KEY missing"},
            )

        import httpx

        # 이미지를 base64로 인코딩
        parts: list[dict] = [{"text": PROMPT}]
        for image_path in images[:4]:
            try:
                path = Path(image_path)
                mime_type, _ = mimetypes.guess_type(path.name)
                mime_type = mime_type or "image/jpeg"
                raw = path.read_bytes()
                encoded = base64.b64encode(raw).decode("utf-8")
                parts.append({
                    "inline_data": {
                        "mime_type": mime_type,
                        "data": encoded,
                    }
                })
            except FileNotFoundError:
                logger.warning("이미지 파일 없음: %s", image_path)
                continue

        # Gemini API 호출
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{settings.gemini_vision_model}:generateContent"
            f"?key={settings.gemini_api_key}"
        )
        payload = {
            "contents": [{"parts": parts}],
            "generationConfig": {
                "temperature": 0.1,
                "maxOutputTokens": 1024,
            },
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(url, json=payload)
                resp.raise_for_status()
                data = resp.json()

            # 응답 파싱
            candidates_resp = data.get("candidates", [])
            if not candidates_resp:
                raise ValueError("Gemini 응답에 candidates가 없습니다")

            text = candidates_resp[0].get("content", {}).get("parts", [{}])[0].get("text", "")
            parsed = _extract_json(text)

            logger.info("gemini_vision_success candidates=%d", len(parsed.get("candidates", [])))
            return ProductIdentityResult(
                candidates=parsed.get("candidates", []),
                confirmed_hint=parsed.get("confirmed_hint"),
                raw_response={"provider": "gemini", "text": text},
            )

        except Exception as e:
            logger.error("gemini_vision_failed error=%s", e)
            return ProductIdentityResult(
                candidates=[{
                    "brand": "Unknown",
                    "model": "Unknown",
                    "category": "unknown",
                    "confidence": 0.1,
                }],
                confirmed_hint=None,
                raw_response={"provider": "gemini", "error": str(e)},
            )
