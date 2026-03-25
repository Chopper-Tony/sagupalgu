"""
Gemini Vision Provider — 미구현 (mock).

현재 Vision AI는 OpenAI provider만 실동작.
VISION_PROVIDER=openai로 설정하세요.
이 모듈은 향후 Gemini Vision API 연동 시 교체 예정.
"""
import logging

from app.vision.vision_provider import ProductIdentityResult, VisionProvider

logger = logging.getLogger(__name__)


class GeminiVisionProvider(VisionProvider):
    async def identify_product(self, images: list[str]) -> ProductIdentityResult:
        logger.warning("GeminiVisionProvider는 미구현 mock입니다. VISION_PROVIDER=openai 권장.")
        return ProductIdentityResult(
            candidates=[
                {
                    "brand": "Unknown",
                    "model": "Unknown",
                    "category": "unknown",
                    "confidence": 0.1,
                }
            ],
            confirmed_hint=None,
            raw_response={"provider": "gemini", "mock": True, "reason": "미구현 — openai 사용 권장"},
        )
