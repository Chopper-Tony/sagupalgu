"""
listing_llm unit 테스트

mock httpx로 외부 HTTP 호출을 차단하고 아래 시나리오를 검증한다:
- build_template_copy: 규칙 기반 폴백 출력
- generate_copy_with_openai: 정상 응답, 429 재시도, 키 미설정 오류
- generate_copy_with_gemini: 정상 응답, candidates 없음 오류, 키 미설정 오류
- generate_copy_with_solar: 정상 응답, 키 미설정 오류
- generate_copy: provider fallback (primary → 나머지 → template)
"""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.listing_llm import (
    build_template_copy,
    generate_copy,
    generate_copy_with_gemini,
    generate_copy_with_openai,
    generate_copy_with_solar,
)


# ── 공통 픽스처 ────────────────────────────────────────────────────

@pytest.fixture
def product():
    return {"brand": "Apple", "model": "iPhone 15 Pro", "category": "smartphone"}


@pytest.fixture
def market():
    return {"median_price": 980000, "price_band": [900000, 1100000]}


@pytest.fixture
def strategy():
    return {"goal": "fast_sell", "recommended_price": 950600}


@pytest.fixture
def llm_json_response():
    return json.dumps({
        "title": "iPhone 15 Pro 256GB 판매합니다",
        "description": "상태 좋습니다.",
        "tags": ["iPhone", "Apple"],
        "price": 950000,
    })


def _make_openai_response(content: str) -> MagicMock:
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {
        "choices": [{"message": {"content": content}}]
    }
    return resp


def _make_gemini_response(text: str) -> MagicMock:
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {
        "candidates": [{"content": {"parts": [{"text": text}]}}]
    }
    return resp


# ─────────────────────────────────────────────────────────────────
# build_template_copy
# ─────────────────────────────────────────────────────────────────

class TestBuildTemplateCopy:

    @pytest.mark.unit
    def test_title_includes_brand_and_model(self, product, market, strategy):
        result = build_template_copy(product, market, strategy)
        assert "Apple" in result["title"]
        assert "iPhone 15 Pro" in result["title"]

    @pytest.mark.unit
    def test_unknown_brand_excluded_from_title(self, market, strategy):
        p = {"brand": "Unknown", "model": "갤럭시 S24", "category": "smartphone"}
        result = build_template_copy(p, market, strategy)
        assert "Unknown" not in result["title"]
        assert "갤럭시 S24" in result["title"]

    @pytest.mark.unit
    def test_description_includes_price_line(self, product, market, strategy):
        result = build_template_copy(product, market, strategy)
        assert "950,600" in result["description"]

    @pytest.mark.unit
    def test_description_uses_median_when_no_recommended(self, product, market):
        s = {"goal": "fast_sell", "recommended_price": 0}
        result = build_template_copy(product, market, s)
        assert "980,000" in result["description"]

    @pytest.mark.unit
    def test_tags_deduped_and_max_five(self, market, strategy):
        p = {"brand": "Apple", "model": "Apple", "category": "smartphone"}
        result = build_template_copy(p, market, strategy)
        assert len(result["tags"]) <= 5
        assert len(result["tags"]) == len(set(result["tags"]))

    @pytest.mark.unit
    def test_price_band_line_in_description(self, product, market, strategy):
        result = build_template_copy(product, market, strategy)
        assert "900,000" in result["description"]
        assert "1,100,000" in result["description"]

    @pytest.mark.unit
    def test_empty_brand_handled(self, market, strategy):
        p = {"brand": "", "model": "갤탭", "category": "tablet"}
        result = build_template_copy(p, market, strategy)
        assert result["title"] == "갤탭 판매합니다"


# ─────────────────────────────────────────────────────────────────
# generate_copy_with_openai
# ─────────────────────────────────────────────────────────────────

class TestGenerateCopyWithOpenai:

    @pytest.mark.unit
    async def test_returns_parsed_json(self, product, market, strategy, llm_json_response):
        mock_resp = _make_openai_response(llm_json_response)
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_resp)

        with patch("app.services.listing_llm.settings") as mock_settings, \
             patch("app.services.listing_llm.httpx.AsyncClient", return_value=mock_client):
            mock_settings.openai_api_key = "sk-test"
            mock_settings.openai_listing_model = "gpt-4o"
            result = await generate_copy_with_openai(product, market, strategy, [])

        assert result["title"] == "iPhone 15 Pro 256GB 판매합니다"

    @pytest.mark.unit
    async def test_raises_when_no_api_key(self, product, market, strategy):
        with patch("app.services.listing_llm.settings") as mock_settings:
            mock_settings.openai_api_key = None
            with pytest.raises(ValueError, match="OPENAI_API_KEY"):
                await generate_copy_with_openai(product, market, strategy, [])

    @pytest.mark.unit
    async def test_retries_on_429_then_succeeds(self, product, market, strategy, llm_json_response):
        import httpx

        fail_resp = MagicMock()
        fail_resp.status_code = 429
        http_error = httpx.HTTPStatusError("429", request=MagicMock(), response=fail_resp)

        ok_resp = _make_openai_response(llm_json_response)

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(side_effect=[http_error, ok_resp])

        with patch("app.services.listing_llm.settings") as mock_settings, \
             patch("app.services.listing_llm.httpx.AsyncClient", return_value=mock_client), \
             patch("app.services.listing_llm.asyncio.sleep", new_callable=AsyncMock):
            mock_settings.openai_api_key = "sk-test"
            mock_settings.openai_listing_model = "gpt-4o"
            result = await generate_copy_with_openai(product, market, strategy, [])

        assert "title" in result


# ─────────────────────────────────────────────────────────────────
# generate_copy_with_gemini
# ─────────────────────────────────────────────────────────────────

class TestGenerateCopyWithGemini:

    @pytest.mark.unit
    async def test_returns_parsed_json(self, product, market, strategy, llm_json_response):
        mock_resp = _make_gemini_response(llm_json_response)
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_resp)

        with patch("app.services.listing_llm.settings") as mock_settings, \
             patch("app.services.listing_llm.httpx.AsyncClient", return_value=mock_client):
            mock_settings.gemini_api_key = "AIza-test"
            mock_settings.gemini_listing_model = "gemini-2.5-flash"
            result = await generate_copy_with_gemini(product, market, strategy, [])

        assert result["title"] == "iPhone 15 Pro 256GB 판매합니다"

    @pytest.mark.unit
    async def test_raises_when_no_api_key(self, product, market, strategy):
        with patch("app.services.listing_llm.settings") as mock_settings:
            mock_settings.gemini_api_key = None
            with pytest.raises(ValueError, match="GEMINI_API_KEY"):
                await generate_copy_with_gemini(product, market, strategy, [])

    @pytest.mark.unit
    async def test_raises_when_no_candidates(self, product, market, strategy):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"candidates": []}

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_resp)

        with patch("app.services.listing_llm.settings") as mock_settings, \
             patch("app.services.listing_llm.httpx.AsyncClient", return_value=mock_client):
            mock_settings.gemini_api_key = "AIza-test"
            mock_settings.gemini_listing_model = "gemini-2.5-flash"
            with pytest.raises(ValueError, match="no candidates"):
                await generate_copy_with_gemini(product, market, strategy, [])

    @pytest.mark.unit
    async def test_raises_when_no_listing_model(self, product, market, strategy):
        with patch("app.services.listing_llm.settings") as mock_settings:
            mock_settings.gemini_api_key = "AIza-test"
            mock_settings.gemini_listing_model = None
            with pytest.raises(ValueError, match="GEMINI_LISTING_MODEL"):
                await generate_copy_with_gemini(product, market, strategy, [])


# ─────────────────────────────────────────────────────────────────
# generate_copy_with_solar
# ─────────────────────────────────────────────────────────────────

class TestGenerateCopyWithSolar:

    @pytest.mark.unit
    async def test_returns_parsed_json(self, product, market, strategy, llm_json_response):
        mock_resp = _make_openai_response(llm_json_response)
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_resp)

        with patch("app.services.listing_llm.settings") as mock_settings, \
             patch("app.services.listing_llm.httpx.AsyncClient", return_value=mock_client):
            mock_settings.upstage_api_key = "up-test"
            mock_settings.solar_listing_model = "solar-1-mini-chat"
            result = await generate_copy_with_solar(product, market, strategy, [])

        assert result["title"] == "iPhone 15 Pro 256GB 판매합니다"

    @pytest.mark.unit
    async def test_raises_when_no_api_key(self, product, market, strategy):
        with patch("app.services.listing_llm.settings") as mock_settings:
            mock_settings.upstage_api_key = None
            with pytest.raises(ValueError, match="UPSTAGE_API_KEY"):
                await generate_copy_with_solar(product, market, strategy, [])

    @pytest.mark.unit
    async def test_raises_when_no_solar_model(self, product, market, strategy):
        with patch("app.services.listing_llm.settings") as mock_settings:
            mock_settings.upstage_api_key = "up-test"
            mock_settings.solar_listing_model = None
            with pytest.raises(ValueError, match="SOLAR_LISTING_MODEL"):
                await generate_copy_with_solar(product, market, strategy, [])


# ─────────────────────────────────────────────────────────────────
# generate_copy (fallback dispatch)
# ─────────────────────────────────────────────────────────────────

class TestGenerateCopy:

    @pytest.mark.unit
    async def test_uses_primary_provider(self, product, market, strategy, llm_json_response):
        with patch("app.services.listing_llm.settings") as mock_settings, \
             patch("app.services.listing_llm.generate_copy_with_gemini", new_callable=AsyncMock) as mock_gemini:
            mock_settings.listing_llm_provider = "gemini"
            mock_gemini.return_value = {"title": "gemini result", "description": "", "tags": [], "price": 0}
            result = await generate_copy(product, market, strategy, [])

        assert result["title"] == "gemini result"
        mock_gemini.assert_called_once()

    @pytest.mark.unit
    async def test_falls_back_to_second_provider(self, product, market, strategy, llm_json_response):
        with patch("app.services.listing_llm.settings") as mock_settings, \
             patch("app.services.listing_llm.generate_copy_with_openai", side_effect=Exception("fail")), \
             patch("app.services.listing_llm.generate_copy_with_gemini", new_callable=AsyncMock) as mock_gemini:
            mock_settings.listing_llm_provider = "openai"
            mock_gemini.return_value = {"title": "fallback", "description": "", "tags": [], "price": 0}
            result = await generate_copy(product, market, strategy, [])

        assert result["title"] == "fallback"

    @pytest.mark.unit
    async def test_returns_template_when_all_fail(self, product, market, strategy):
        with patch("app.services.listing_llm.settings") as mock_settings, \
             patch("app.services.listing_llm.generate_copy_with_openai", side_effect=Exception), \
             patch("app.services.listing_llm.generate_copy_with_gemini", side_effect=Exception), \
             patch("app.services.listing_llm.generate_copy_with_solar", side_effect=Exception):
            mock_settings.listing_llm_provider = "openai"
            result = await generate_copy(product, market, strategy, [])

        assert "title" in result
        assert "iPhone 15 Pro" in result["title"]

    @pytest.mark.unit
    async def test_unknown_primary_defaults_to_openai_order(self, product, market, strategy):
        with patch("app.services.listing_llm.settings") as mock_settings, \
             patch("app.services.listing_llm.generate_copy_with_openai", new_callable=AsyncMock) as mock_openai:
            mock_settings.listing_llm_provider = "unknown_provider"
            mock_openai.return_value = {"title": "ok", "description": "", "tags": [], "price": 0}
            result = await generate_copy(product, market, strategy, [])

        mock_openai.assert_called_once()
        assert result["title"] == "ok"
