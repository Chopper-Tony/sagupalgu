"""
ProductService 통합 테스트

Vision API는 mock 처리하고 ProductService의 provider 라우팅 로직을 검증한다:
- settings.vision_provider=="openai" → OpenAIVisionProvider 사용
- settings.vision_provider=="gemini" → GeminiVisionProvider 사용
- identify_product 호출 위임 확인
- Vision 실패 시 에러 전파
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.product_service import ProductService
from app.vision.vision_provider import ProductIdentityResult


# ── 공통 픽스처 ──────────────────────────────────────────────────────

@pytest.fixture
def image_paths():
    return ["/uploads/product1.jpg", "/uploads/product2.jpg"]


@pytest.fixture
def vision_result():
    """Vision AI 정상 응답."""
    return ProductIdentityResult(
        candidates=[
            {
                "brand": "Apple",
                "model": "iPhone 15 Pro",
                "category": "smartphone",
                "confidence": 0.92,
            },
            {
                "brand": "Apple",
                "model": "iPhone 15",
                "category": "smartphone",
                "confidence": 0.75,
            },
        ],
        confirmed_hint=None,
        raw_response={"source": "mock"},
    )


@pytest.fixture
def svc():
    return ProductService()


# ── Provider 라우팅 테스트 ───────────────────────────────────────────

@pytest.mark.integration
class TestVisionProviderRouting:
    """settings.vision_provider에 따라 올바른 provider가 선택되는지 검증."""

    def test_openai_provider_선택(self, svc):
        """vision_provider=="openai" → OpenAIVisionProvider 인스턴스."""
        with patch("app.services.product_service.settings") as mock_settings:
            mock_settings.vision_provider = "openai"
            provider = svc.get_vision_provider()

        from app.vision.openai_provider import OpenAIVisionProvider
        assert isinstance(provider, OpenAIVisionProvider)

    def test_gemini_provider_선택(self, svc):
        """vision_provider=="gemini" → GeminiVisionProvider 인스턴스."""
        with patch("app.services.product_service.settings") as mock_settings:
            mock_settings.vision_provider = "gemini"
            provider = svc.get_vision_provider()

        from app.vision.gemini_provider import GeminiVisionProvider
        assert isinstance(provider, GeminiVisionProvider)

    def test_기본값은_openai(self, svc):
        """vision_provider가 알 수 없는 값이면 OpenAI fallback."""
        with patch("app.services.product_service.settings") as mock_settings:
            mock_settings.vision_provider = "unknown_provider"
            provider = svc.get_vision_provider()

        from app.vision.openai_provider import OpenAIVisionProvider
        assert isinstance(provider, OpenAIVisionProvider)


# ── identify_product 위임 테스트 ─────────────────────────────────────

@pytest.mark.integration
class TestIdentifyProduct:
    """identify_product가 provider에 올바르게 위임하는지 검증."""

    async def test_identify_product_정상_위임(self, svc, image_paths, vision_result):
        """provider.identify_product가 호출되고 결과가 그대로 반환."""
        mock_provider = AsyncMock()
        mock_provider.identify_product = AsyncMock(return_value=vision_result)

        with patch.object(svc, "get_vision_provider", return_value=mock_provider):
            result = await svc.identify_product(image_paths)

        mock_provider.identify_product.assert_called_once_with(image_paths)
        assert result == vision_result
        assert len(result.candidates) == 2
        assert result.candidates[0]["brand"] == "Apple"

    async def test_identify_product_candidates_shape(self, svc, image_paths, vision_result):
        """반환값이 ProductIdentityResult 타입이고 candidates 구조가 올바른지."""
        mock_provider = AsyncMock()
        mock_provider.identify_product = AsyncMock(return_value=vision_result)

        with patch.object(svc, "get_vision_provider", return_value=mock_provider):
            result = await svc.identify_product(image_paths)

        assert isinstance(result, ProductIdentityResult)
        for candidate in result.candidates:
            assert "brand" in candidate
            assert "model" in candidate
            assert "confidence" in candidate

    async def test_단일_이미지로도_호출_가능(self, svc, vision_result):
        """이미지 1개만 전달해도 정상 동작."""
        mock_provider = AsyncMock()
        mock_provider.identify_product = AsyncMock(return_value=vision_result)

        with patch.object(svc, "get_vision_provider", return_value=mock_provider):
            result = await svc.identify_product(["/uploads/single.jpg"])

        mock_provider.identify_product.assert_called_once_with(["/uploads/single.jpg"])
        assert result.candidates is not None


# ── Vision 실패 시 에러 전파 테스트 ──────────────────────────────────

@pytest.mark.integration
class TestVisionErrorPropagation:
    """Vision API 실패 시 에러가 호출자에게 전파되는지 검증."""

    async def test_vision_api_에러_전파(self, svc, image_paths):
        """provider가 예외를 발생시키면 그대로 전파."""
        mock_provider = AsyncMock()
        mock_provider.identify_product = AsyncMock(
            side_effect=ValueError("Vision API key not configured")
        )

        with patch.object(svc, "get_vision_provider", return_value=mock_provider):
            with pytest.raises(ValueError, match="Vision API key not configured"):
                await svc.identify_product(image_paths)

    async def test_vision_timeout_에러_전파(self, svc, image_paths):
        """타임아웃 에러도 전파."""
        mock_provider = AsyncMock()
        mock_provider.identify_product = AsyncMock(
            side_effect=TimeoutError("Vision API timeout")
        )

        with patch.object(svc, "get_vision_provider", return_value=mock_provider):
            with pytest.raises(TimeoutError, match="Vision API timeout"):
                await svc.identify_product(image_paths)

    async def test_빈_이미지_리스트(self, svc):
        """빈 이미지 리스트로 호출해도 provider에 그대로 위임."""
        empty_result = ProductIdentityResult(candidates=[], confirmed_hint=None)
        mock_provider = AsyncMock()
        mock_provider.identify_product = AsyncMock(return_value=empty_result)

        with patch.object(svc, "get_vision_provider", return_value=mock_provider):
            result = await svc.identify_product([])

        assert result.candidates == []
        mock_provider.identify_product.assert_called_once_with([])
