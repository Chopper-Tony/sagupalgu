"""
도메인 규칙 테스트 (순수 단위)

외부 의존성 없음. product_rules.py의 모든 규칙을 코드로 잠근다.
- normalize_text
- needs_user_input
- build_confirmed_product_from_candidate
- build_confirmed_product_from_user_input
"""
import pytest

from app.domain.product_rules import (
    CONFIDENCE_THRESHOLD,
    build_confirmed_product_from_candidate,
    build_confirmed_product_from_user_input,
    needs_user_input,
    normalize_text,
)


# ─────────────────────────────────────────────────────────────────
# normalize_text
# ─────────────────────────────────────────────────────────────────

class TestNormalizeText:

    @pytest.mark.unit
    def test_none_returns_empty(self):
        assert normalize_text(None) == ""

    @pytest.mark.unit
    def test_empty_string_returns_empty(self):
        assert normalize_text("") == ""

    @pytest.mark.unit
    def test_whitespace_returns_empty(self):
        assert normalize_text("   ") == ""

    @pytest.mark.unit
    def test_unknown_returns_empty(self):
        assert normalize_text("unknown") == ""
        assert normalize_text("Unknown") == ""
        assert normalize_text("UNKNOWN") == ""

    @pytest.mark.unit
    def test_none_string_returns_empty(self):
        assert normalize_text("none") == ""
        assert normalize_text("None") == ""

    @pytest.mark.unit
    def test_null_string_returns_empty(self):
        assert normalize_text("null") == ""

    @pytest.mark.unit
    def test_na_returns_empty(self):
        assert normalize_text("n/a") == ""

    @pytest.mark.unit
    def test_valid_text_returned_stripped(self):
        assert normalize_text("  iPhone 15  ") == "iPhone 15"

    @pytest.mark.unit
    def test_valid_text_unchanged(self):
        assert normalize_text("Galaxy S24") == "Galaxy S24"


# ─────────────────────────────────────────────────────────────────
# needs_user_input
# ─────────────────────────────────────────────────────────────────

class TestNeedsUserInput:

    @pytest.mark.unit
    def test_high_confidence_with_all_fields_no_input_needed(self):
        candidate = {"brand": "Apple", "model": "iPhone 15", "category": "smartphone", "confidence": 0.9}
        assert needs_user_input(candidate) is False

    @pytest.mark.unit
    def test_confidence_below_threshold_needs_input(self):
        candidate = {"brand": "Apple", "model": "iPhone 15", "category": "smartphone", "confidence": 0.5}
        assert needs_user_input(candidate) is True

    @pytest.mark.unit
    def test_confidence_exactly_at_threshold_no_input(self):
        candidate = {"brand": "Apple", "model": "iPhone 15", "category": "smartphone", "confidence": CONFIDENCE_THRESHOLD}
        assert needs_user_input(candidate) is False

    @pytest.mark.unit
    def test_missing_model_needs_input(self):
        candidate = {"brand": "Apple", "model": "", "category": "smartphone", "confidence": 0.9}
        assert needs_user_input(candidate) is True

    @pytest.mark.unit
    def test_unknown_model_needs_input(self):
        candidate = {"brand": "Apple", "model": "unknown", "category": "smartphone", "confidence": 0.9}
        assert needs_user_input(candidate) is True

    @pytest.mark.unit
    def test_missing_brand_and_category_needs_input(self):
        candidate = {"brand": "", "model": "iPhone 15", "category": "", "confidence": 0.9}
        assert needs_user_input(candidate) is True

    @pytest.mark.unit
    def test_missing_brand_but_has_category_no_input(self):
        candidate = {"brand": "", "model": "iPhone 15", "category": "smartphone", "confidence": 0.9}
        assert needs_user_input(candidate) is False

    @pytest.mark.unit
    def test_missing_category_but_has_brand_no_input(self):
        candidate = {"brand": "Apple", "model": "iPhone 15", "category": "", "confidence": 0.9}
        assert needs_user_input(candidate) is False

    @pytest.mark.unit
    def test_zero_confidence_needs_input(self):
        candidate = {"brand": "Apple", "model": "iPhone 15", "category": "smartphone", "confidence": 0.0}
        assert needs_user_input(candidate) is True

    @pytest.mark.unit
    def test_empty_candidate_needs_input(self):
        assert needs_user_input({}) is True


# ─────────────────────────────────────────────────────────────────
# build_confirmed_product_from_candidate
# ─────────────────────────────────────────────────────────────────

class TestBuildFromCandidate:

    @pytest.mark.unit
    def test_basic_fields_mapped(self):
        candidate = {"brand": "Apple", "model": "iPhone 15", "category": "smartphone", "confidence": 0.92}
        result = build_confirmed_product_from_candidate(candidate)
        assert result["brand"] == "Apple"
        assert result["model"] == "iPhone 15"
        assert result["category"] == "smartphone"
        assert result["confidence"] == 0.92

    @pytest.mark.unit
    def test_source_defaults_to_vision(self):
        candidate = {"brand": "Apple", "model": "iPhone 15", "category": "smartphone", "confidence": 0.9}
        result = build_confirmed_product_from_candidate(candidate)
        assert result["source"] == "vision"

    @pytest.mark.unit
    def test_source_preserved_when_provided(self):
        candidate = {"brand": "Apple", "model": "iPhone 15", "category": "smartphone", "confidence": 0.9, "source": "user_input"}
        result = build_confirmed_product_from_candidate(candidate)
        assert result["source"] == "user_input"

    @pytest.mark.unit
    def test_storage_defaults_to_empty(self):
        candidate = {"brand": "Apple", "model": "iPhone 15", "category": "smartphone", "confidence": 0.9}
        result = build_confirmed_product_from_candidate(candidate)
        assert result["storage"] == ""

    @pytest.mark.unit
    def test_storage_preserved_when_provided(self):
        candidate = {"brand": "Apple", "model": "iPhone 15", "category": "smartphone", "confidence": 0.9, "storage": "256GB"}
        result = build_confirmed_product_from_candidate(candidate)
        assert result["storage"] == "256GB"

    @pytest.mark.unit
    def test_missing_confidence_defaults_to_zero(self):
        candidate = {"brand": "Apple", "model": "iPhone 15", "category": "smartphone"}
        result = build_confirmed_product_from_candidate(candidate)
        assert result["confidence"] == 0.0

    @pytest.mark.unit
    def test_none_confidence_defaults_to_zero(self):
        candidate = {"brand": "Apple", "model": "iPhone 15", "category": "smartphone", "confidence": None}
        result = build_confirmed_product_from_candidate(candidate)
        assert result["confidence"] == 0.0


# ─────────────────────────────────────────────────────────────────
# build_confirmed_product_from_user_input
# ─────────────────────────────────────────────────────────────────

class TestBuildFromUserInput:

    @pytest.mark.unit
    def test_basic_fields(self):
        result = build_confirmed_product_from_user_input(model="iPhone 15", brand="Apple", category="smartphone")
        assert result["model"] == "iPhone 15"
        assert result["brand"] == "Apple"
        assert result["category"] == "smartphone"

    @pytest.mark.unit
    def test_source_is_user_input(self):
        result = build_confirmed_product_from_user_input(model="iPhone 15")
        assert result["source"] == "user_input"

    @pytest.mark.unit
    def test_confidence_is_one(self):
        result = build_confirmed_product_from_user_input(model="iPhone 15")
        assert result["confidence"] == 1.0

    @pytest.mark.unit
    def test_missing_brand_defaults_to_unknown(self):
        result = build_confirmed_product_from_user_input(model="iPhone 15", brand=None)
        assert result["brand"] == "Unknown"

    @pytest.mark.unit
    def test_missing_category_defaults_to_unknown(self):
        result = build_confirmed_product_from_user_input(model="iPhone 15", category=None)
        assert result["category"] == "unknown"

    @pytest.mark.unit
    def test_empty_model_raises(self):
        with pytest.raises(ValueError, match="모델명은 필수"):
            build_confirmed_product_from_user_input(model="")

    @pytest.mark.unit
    def test_unknown_model_raises(self):
        with pytest.raises(ValueError, match="모델명은 필수"):
            build_confirmed_product_from_user_input(model="unknown")

    @pytest.mark.unit
    def test_whitespace_model_raises(self):
        with pytest.raises(ValueError, match="모델명은 필수"):
            build_confirmed_product_from_user_input(model="   ")

    @pytest.mark.unit
    def test_model_is_stripped(self):
        result = build_confirmed_product_from_user_input(model="  iPhone 15  ")
        assert result["model"] == "iPhone 15"
