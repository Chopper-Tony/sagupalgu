from app.core.config import settings
from app.vision.openai_provider import OpenAIVisionProvider
from app.vision.gemini_provider import GeminiVisionProvider
from app.vision.vision_provider import VisionProvider, ProductIdentityResult

class ProductService:
    def get_vision_provider(self) -> VisionProvider:
        if settings.vision_provider == "gemini":
            return GeminiVisionProvider()
        return OpenAIVisionProvider()

    async def identify_product(self, image_paths: list[str]) -> ProductIdentityResult:
        provider = self.get_vision_provider()
        return await provider.identify_product(image_paths)
