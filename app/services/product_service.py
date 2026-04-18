"""상품 식별 서비스.

Vision provider를 순회하며 fallback 체인으로 상품을 식별한다.
`_build_react_llm()` 의 provider 순회 패턴을 그대로 이식.
"""
from __future__ import annotations

import logging

from app.core.config import settings
from app.vision.gemini_provider import GeminiVisionProvider
from app.vision.openai_provider import OpenAIVisionProvider
from app.vision.vision_provider import ProductIdentityResult, VisionProvider

logger = logging.getLogger(__name__)


class ProductService:
    def get_vision_provider(self) -> VisionProvider:
        """Primary provider 선택 (단일 사용 경로 호환용).

        실제 `identify_product()` 는 fallback 체인을 순회하므로 이 메서드는
        주로 기존 테스트·단일 provider 호출 시에만 쓰인다.
        """
        if settings.vision_provider == "gemini":
            return GeminiVisionProvider()
        return OpenAIVisionProvider()

    def _provider_order(self) -> list[str]:
        """`VISION_PROVIDER` 설정 기반 provider 순회 순서."""
        if settings.vision_provider == "openai":
            return ["openai", "gemini"]
        # 기본(gemini) 또는 알 수 없는 값 → Gemini 우선, OpenAI fallback
        return ["gemini", "openai"]

    def _build_provider(self, name: str) -> VisionProvider | None:
        """Provider 생성 시도. API 키 미설정·Import 실패 시 None 반환."""
        try:
            if name == "gemini" and settings.gemini_api_key:
                return GeminiVisionProvider()
            if name == "openai" and settings.openai_api_key:
                return OpenAIVisionProvider()
        except (ImportError, ValueError, RuntimeError) as e:
            logger.warning(
                "vision_provider_build_failed provider=%s error=%s",
                name, e,
            )
        return None

    async def identify_product(
        self, image_paths: list[str]
    ) -> ProductIdentityResult:
        """Provider 순회 fallback — 1차 실패 시 2차로 자동 복구.

        Raises:
            RuntimeError: 사용 가능한 provider가 하나도 없을 때.
            Exception: 모든 provider 실행이 실패했을 때 마지막 에러 전파.
        """
        last_error: Exception | None = None
        for name in self._provider_order():
            provider = self._build_provider(name)
            if provider is None:
                continue
            try:
                result = await provider.identify_product(image_paths)
                logger.info("vision_provider_success provider=%s", name)
                return result
            except Exception as e:
                logger.warning(
                    "vision_provider_runtime_failed provider=%s error=%s",
                    name, e,
                )
                last_error = e
                continue

        if last_error is not None:
            raise last_error
        raise RuntimeError(
            "Vision provider 사용 불가 — GEMINI_API_KEY 또는 OPENAI_API_KEY 확인",
        )
