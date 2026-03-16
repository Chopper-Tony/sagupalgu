from app.core.config import settings
from app.vision.vision_provider import ProductIdentityResult, VisionProvider

class GeminiVisionProvider(VisionProvider):
    async def identify_product(self, images: list[str]) -> ProductIdentityResult:
        # TODO: 실제 Gemini vision 연결 검증 후 교체
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
            raw_response={"provider": "gemini", "mock": True, "reason": "TODO real implementation"},
        )
