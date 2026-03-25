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
You are a marketplace product identification assistant.
Given one or more product photos, identify the product and return STRICT JSON.

Return schema:
{
  "candidates": [
    {
      "brand": "string",
      "model": "string",
      "category": "string",
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
