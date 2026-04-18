"""
ProductService 통합 테스트

Vision API는 mock 처리하고 ProductService의 provider fallback 체인을 검증한다:
- settings.vision_provider=="gemini" → Gemini 우선, OpenAI fallback
- settings.vision_provider=="openai" → OpenAI 우선, Gemini fallback
- 1차 provider 런타임 실패 시 2차로 자동 복구
- 모든 provider 실패 시 마지막 에러 전파
- 사용 가능한 provider가 없으면 RuntimeError
"""
import pytest
from unittest.mock import AsyncMock, patch

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


# ── Provider 라우팅 테스트 (기본 primary 선택) ────────────────────────

@pytest.mark.integration
class TestVisionProviderRouting:
    """get_vision_provider()가 settings.vision_provider에 따라 primary를 선택하는지 검증."""

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

    def test_알_수_없는_provider면_openai(self, svc):
        """vision_provider가 알 수 없는 값이면 OpenAI fallback (기본 분기)."""
        with patch("app.services.product_service.settings") as mock_settings:
            mock_settings.vision_provider = "unknown_provider"
            provider = svc.get_vision_provider()

        from app.vision.openai_provider import OpenAIVisionProvider
        assert isinstance(provider, OpenAIVisionProvider)


# ── Provider 순회 순서 테스트 ────────────────────────────────────────

@pytest.mark.integration
class TestProviderOrder:
    """_provider_order()가 설정 기반으로 올바른 순회 순서를 반환하는지 검증."""

    def test_gemini_기본_순서는_gemini_openai(self, svc):
        with patch("app.services.product_service.settings") as mock_settings:
            mock_settings.vision_provider = "gemini"
            assert svc._provider_order() == ["gemini", "openai"]

    def test_openai_설정_시_openai_gemini(self, svc):
        with patch("app.services.product_service.settings") as mock_settings:
            mock_settings.vision_provider = "openai"
            assert svc._provider_order() == ["openai", "gemini"]

    def test_알_수_없는_값은_gemini_우선(self, svc):
        with patch("app.services.product_service.settings") as mock_settings:
            mock_settings.vision_provider = "unknown"
            assert svc._provider_order() == ["gemini", "openai"]


# ── identify_product fallback 체인 테스트 ───────────────────────────

@pytest.mark.integration
class TestIdentifyProductFallback:
    """identify_product가 순회 fallback으로 정상·예외 시나리오를 처리하는지 검증."""

    async def test_1차_provider_성공(self, svc, image_paths, vision_result):
        """1차 provider가 성공하면 2차는 호출되지 않음."""
        gemini_mock = AsyncMock()
        gemini_mock.identify_product = AsyncMock(return_value=vision_result)

        def build(name: str):
            return gemini_mock if name == "gemini" else None

        with patch("app.services.product_service.settings") as mock_settings, \
             patch.object(svc, "_build_provider", side_effect=build):
            mock_settings.vision_provider = "gemini"
            result = await svc.identify_product(image_paths)

        gemini_mock.identify_product.assert_called_once_with(image_paths)
        assert result == vision_result

    async def test_1차_실패_시_2차로_fallback(self, svc, image_paths, vision_result):
        """1차 provider가 런타임 에러를 내면 2차가 호출되고 성공 결과 반환."""
        gemini_mock = AsyncMock()
        gemini_mock.identify_product = AsyncMock(
            side_effect=ValueError("Gemini API rate limit"),
        )
        openai_mock = AsyncMock()
        openai_mock.identify_product = AsyncMock(return_value=vision_result)

        def build(name: str):
            return gemini_mock if name == "gemini" else openai_mock

        with patch("app.services.product_service.settings") as mock_settings, \
             patch.object(svc, "_build_provider", side_effect=build):
            mock_settings.vision_provider = "gemini"
            result = await svc.identify_product(image_paths)

        gemini_mock.identify_product.assert_called_once()
        openai_mock.identify_product.assert_called_once()
        assert result == vision_result

    async def test_양쪽_모두_실패_시_마지막_에러_전파(self, svc, image_paths):
        """1·2차 모두 실패하면 마지막(2차) 에러가 raise 됨."""
        gemini_mock = AsyncMock()
        gemini_mock.identify_product = AsyncMock(
            side_effect=ValueError("Gemini fail"),
        )
        openai_mock = AsyncMock()
        openai_mock.identify_product = AsyncMock(
            side_effect=TimeoutError("OpenAI timeout"),
        )

        def build(name: str):
            return gemini_mock if name == "gemini" else openai_mock

        with patch("app.services.product_service.settings") as mock_settings, \
             patch.object(svc, "_build_provider", side_effect=build):
            mock_settings.vision_provider = "gemini"
            with pytest.raises(TimeoutError, match="OpenAI timeout"):
                await svc.identify_product(image_paths)

    async def test_provider_없으면_RuntimeError(self, svc, image_paths):
        """모든 provider가 키 미설정 등으로 생성 실패하면 RuntimeError."""
        with patch("app.services.product_service.settings") as mock_settings, \
             patch.object(svc, "_build_provider", return_value=None):
            mock_settings.vision_provider = "gemini"
            with pytest.raises(RuntimeError, match="Vision provider"):
                await svc.identify_product(image_paths)

    async def test_단일_이미지로도_호출_가능(self, svc, vision_result):
        """이미지 1개만 전달해도 정상 동작."""
        provider_mock = AsyncMock()
        provider_mock.identify_product = AsyncMock(return_value=vision_result)

        with patch("app.services.product_service.settings") as mock_settings, \
             patch.object(svc, "_build_provider", return_value=provider_mock):
            mock_settings.vision_provider = "gemini"
            result = await svc.identify_product(["/uploads/single.jpg"])

        provider_mock.identify_product.assert_called_once_with(["/uploads/single.jpg"])
        assert isinstance(result, ProductIdentityResult)

    async def test_빈_이미지_리스트(self, svc):
        """빈 이미지 리스트로 호출해도 provider에 그대로 위임."""
        empty_result = ProductIdentityResult(candidates=[], confirmed_hint=None)
        provider_mock = AsyncMock()
        provider_mock.identify_product = AsyncMock(return_value=empty_result)

        with patch("app.services.product_service.settings") as mock_settings, \
             patch.object(svc, "_build_provider", return_value=provider_mock):
            mock_settings.vision_provider = "gemini"
            result = await svc.identify_product([])

        assert result.candidates == []
        provider_mock.identify_product.assert_called_once_with([])
