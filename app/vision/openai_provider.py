import base64
import json
import mimetypes
import re
from pathlib import Path

from app.core.config import settings
from app.vision.vision_provider import ProductIdentityResult, VisionProvider

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
