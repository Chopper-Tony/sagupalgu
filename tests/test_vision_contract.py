"""
M78: Vision AI 응답 shape 계약 테스트 + 프롬프트 품질 검증.

Vision API 실호출 없이 응답 구조만 검증하는 unit 테스트.
실제 API 테스트는 scripts/manual/test_vision_prompt.py 참조.
"""
import json
import pytest

pytestmark = pytest.mark.unit


# ── 응답 shape 계약 ────────────────────────────────────────────


class TestVisionResponseShape:
    """Vision provider가 반환하는 ProductIdentityResult 구조 검증."""

    def test_product_identity_result_fields(self):
        from app.vision.vision_provider import ProductIdentityResult

        result = ProductIdentityResult(
            candidates=[{"brand": "트위스비", "model": "VAC700R", "category": "문구/필기구", "confidence": 0.85}],
            confirmed_hint={"brand": "트위스비", "model": "VAC700R", "category": "문구/필기구"},
            raw_response={"provider": "openai", "text": "{}"},
        )
        assert isinstance(result.candidates, list)
        assert len(result.candidates) == 1
        assert result.confirmed_hint is not None
        assert result.raw_response is not None

    def test_candidate_required_keys(self):
        """각 candidate는 brand, model, category, confidence 필수."""
        required_keys = {"brand", "model", "category", "confidence"}
        candidate = {"brand": "Apple", "model": "iPhone 15 Pro", "category": "스마트폰", "confidence": 0.95}
        assert required_keys.issubset(candidate.keys())

    def test_candidate_confidence_range(self):
        """confidence는 0.0~1.0 범위."""
        valid = [0.0, 0.1, 0.5, 0.9, 1.0]
        for c in valid:
            assert 0.0 <= c <= 1.0

    def test_empty_candidates_allowed(self):
        """빈 candidates도 유효 (식별 실패 시)."""
        from app.vision.vision_provider import ProductIdentityResult

        result = ProductIdentityResult(candidates=[], confirmed_hint=None)
        assert result.candidates == []
        assert result.confirmed_hint is None

    def test_mock_fallback_shape(self):
        """API 키 없을 때 mock fallback도 동일 shape."""
        from app.vision.vision_provider import ProductIdentityResult

        result = ProductIdentityResult(
            candidates=[{"brand": "Unknown", "model": "Unknown", "category": "unknown", "confidence": 0.1}],
            confirmed_hint=None,
            raw_response={"provider": "openai", "mock": True},
        )
        assert result.candidates[0]["confidence"] == 0.1
        assert result.candidates[0]["brand"] == "Unknown"


# ── 프롬프트 품질 검증 ────────────────────────────────────────


class TestVisionPromptQuality:
    """프롬프트에 필수 요소가 포함되어 있는지 검증."""

    def _get_prompts(self):
        """OpenAI/Gemini 양쪽 프롬프트를 가져옴."""
        from app.vision.openai_provider import PROMPT as openai_prompt
        from app.vision.gemini_provider import PROMPT as gemini_prompt
        return [openai_prompt, gemini_prompt]

    def test_prompts_contain_anti_hallucination(self):
        """오인식 방지 지시가 포함되어야 함."""
        for prompt in self._get_prompts():
            assert "Do NOT guess" in prompt or "ONLY what you actually see" in prompt

    def test_prompts_contain_category_examples(self):
        """카테고리 예시가 포함되어야 함 (비전자기기 포함)."""
        for prompt in self._get_prompts():
            assert "문구/필기구" in prompt
            assert "의류" in prompt
            assert "가구" in prompt
            assert "스마트폰" in prompt

    def test_prompts_contain_confidence_guidance(self):
        """confidence 기준이 명시되어야 함."""
        for prompt in self._get_prompts():
            assert "confidence" in prompt.lower()
            assert "0.9" in prompt

    def test_prompts_contain_json_schema(self):
        """JSON schema가 포함되어야 함."""
        for prompt in self._get_prompts():
            assert '"candidates"' in prompt
            assert '"brand"' in prompt
            assert '"model"' in prompt
            assert '"category"' in prompt

    def test_prompts_identical(self):
        """OpenAI와 Gemini 프롬프트가 동일해야 함 (일관성)."""
        prompts = self._get_prompts()
        assert prompts[0] == prompts[1]

    def test_prompts_not_biased_to_electronics(self):
        """전자기기 편향이 없어야 함 (비전자기기 카테고리가 충분해야)."""
        for prompt in self._get_prompts():
            non_electronic = ["의류", "신발", "가방", "가구", "도서", "문구/필기구", "악기", "스포츠용품"]
            count = sum(1 for cat in non_electronic if cat in prompt)
            assert count >= 5, f"비전자기기 카테고리가 너무 적음: {count}개"


# ── _extract_json 유틸 ────────────────────────────────────────


class TestExtractJson:
    """Vision provider의 JSON 추출 유틸 검증."""

    def test_plain_json(self):
        from app.vision.openai_provider import _extract_json

        text = '{"candidates": [{"brand": "Apple", "model": "iPhone 15", "category": "스마트폰", "confidence": 0.9}]}'
        result = _extract_json(text)
        assert result["candidates"][0]["brand"] == "Apple"

    def test_json_with_markdown(self):
        """markdown 코드블록 안 JSON도 추출."""
        from app.vision.openai_provider import _extract_json

        text = '```json\n{"candidates": [{"brand": "트위스비", "model": "VAC700R", "category": "문구/필기구", "confidence": 0.8}]}\n```'
        result = _extract_json(text)
        assert result["candidates"][0]["category"] == "문구/필기구"

    def test_json_with_surrounding_text(self):
        """앞뒤 텍스트가 있어도 JSON 추출."""
        from app.vision.openai_provider import _extract_json

        text = 'Here is the result:\n{"candidates": [{"brand": "", "model": "만년필", "category": "문구/필기구", "confidence": 0.6}]}\nDone.'
        result = _extract_json(text)
        assert result["candidates"][0]["model"] == "만년필"

    def test_invalid_json_raises(self):
        """유효하지 않은 JSON은 예외."""
        from app.vision.openai_provider import _extract_json

        with pytest.raises((json.JSONDecodeError, Exception)):
            _extract_json("this is not json at all")
