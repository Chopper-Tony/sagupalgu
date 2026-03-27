import base64
import json
import mimetypes
import re
from pathlib import Path

from app.core.config import settings
from app.vision.vision_provider import ProductIdentityResult, VisionProvider

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

def _local_image_to_data_url(image_path: str) -> str:
    path = Path(image_path)
    mime_type, _ = mimetypes.guess_type(path.name)
    mime_type = mime_type or "image/jpeg"
    raw = path.read_bytes()
    encoded = base64.b64encode(raw).decode("utf-8")
    return f"data:{mime_type};base64,{encoded}"

def _extract_json(text: str) -> dict:
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", text)
        if not match:
            raise
        return json.loads(match.group(0))

class OpenAIVisionProvider(VisionProvider):
    async def identify_product(self, images: list[str]) -> ProductIdentityResult:
        if not settings.openai_api_key:
            return ProductIdentityResult(
                candidates=[{
                    "brand": "Unknown",
                    "model": "Unknown",
                    "category": "unknown",
                    "confidence": 0.1,
                }],
                confirmed_hint=None,
                raw_response={"provider": "openai", "mock": True, "reason": "OPENAI_API_KEY missing"},
            )

        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=settings.openai_api_key)

        content = [{"type": "input_text", "text": PROMPT}]
        for image in images[:4]:
            try:
                data_url = _local_image_to_data_url(image)
                content.append({"type": "input_image", "image_url": data_url})
            except FileNotFoundError:
                continue

        response = await client.responses.create(
            model=settings.openai_vision_model,
            input=[{"role": "user", "content": content}],
        )
        output_text = getattr(response, "output_text", "") or ""
        parsed = _extract_json(output_text)

        return ProductIdentityResult(
            candidates=parsed.get("candidates", []),
            confirmed_hint=parsed.get("confirmed_hint"),
            raw_response={"provider": "openai", "text": output_text},
        )
