"""
session_product 순수 함수 unit 테스트.

product_data 조작 함수가 올바른 키를 설정/제거하는지 검증.
"""
import pytest

from app.services.session_product import (
    apply_analysis_result,
    attach_image_paths,
    confirm_from_candidate,
    confirm_from_user_input,
)


class TestAttachImagePaths:

    @pytest.mark.unit
    def test_sets_image_paths(self):
        data = {}
        attach_image_paths(data, ["https://img1.jpg", "https://img2.jpg"])
        assert data["image_paths"] == ["https://img1.jpg", "https://img2.jpg"]

    @pytest.mark.unit
    def test_overwrites_existing(self):
        data = {"image_paths": ["old.jpg"]}
        attach_image_paths(data, ["new.jpg"])
        assert data["image_paths"] == ["new.jpg"]


class TestApplyAnalysisResult:

    @pytest.mark.unit
    def test_sets_candidates_and_source(self):
        data = {}
        candidates = [{"model": "S24", "confidence": 0.95}]
        result, needs_input = apply_analysis_result(data, candidates, ["img.jpg"])
        assert result["candidates"] == candidates
        assert result["analysis_source"] == "vision"
        assert result["image_count"] == 1

    @pytest.mark.unit
    def test_high_confidence_no_input_needed(self):
        data = {}
        candidates = [{"model": "S24", "brand": "Samsung", "category": "phone", "confidence": 0.95}]
        _, needs_input = apply_analysis_result(data, candidates, ["img.jpg"])
        assert needs_input is False
        assert data.get("user_input_prompt") is None

    @pytest.mark.unit
    def test_low_confidence_needs_input(self):
        data = {}
        candidates = [{"model": "?", "confidence": 0.3}]
        _, needs_input = apply_analysis_result(data, candidates, ["img.jpg"])
        assert needs_input is True
        assert "모델명" in data["user_input_prompt"]

    @pytest.mark.unit
    def test_empty_candidates_raises(self):
        with pytest.raises(ValueError, match="상품 인식"):
            apply_analysis_result({}, [], ["img.jpg"])

    @pytest.mark.unit
    def test_removes_prompt_when_high_confidence(self):
        data = {"user_input_prompt": "이전 프롬프트"}
        candidates = [{"model": "S24", "brand": "Samsung", "category": "phone", "confidence": 0.95}]
        apply_analysis_result(data, candidates, ["img.jpg"])
        assert "user_input_prompt" not in data


class TestConfirmFromCandidate:

    @pytest.mark.unit
    def test_confirms_valid_index(self):
        data = {"candidates": [{"model": "A"}, {"model": "B"}]}
        confirm_from_candidate(data, 1)
        assert data["confirmed_product"]["model"] == "B"
        assert data["confirmed_product"]["source"] == "vision"
        assert data["needs_user_input"] is False

    @pytest.mark.unit
    def test_invalid_index_raises(self):
        data = {"candidates": [{"model": "A"}]}
        with pytest.raises(ValueError, match="유효하지 않은"):
            confirm_from_candidate(data, 5)

    @pytest.mark.unit
    def test_negative_index_raises(self):
        data = {"candidates": [{"model": "A"}]}
        with pytest.raises(ValueError, match="유효하지 않은"):
            confirm_from_candidate(data, -1)

    @pytest.mark.unit
    def test_removes_user_input_prompt(self):
        data = {"candidates": [{"model": "A"}], "user_input_prompt": "입력해주세요"}
        confirm_from_candidate(data, 0)
        assert "user_input_prompt" not in data


class TestConfirmFromUserInput:

    @pytest.mark.unit
    def test_creates_confirmed_product(self):
        data = {}
        confirm_from_user_input(data, model="갤럭시 S24", brand="Samsung", category="phone")
        cp = data["confirmed_product"]
        assert cp["model"] == "갤럭시 S24"
        assert cp["brand"] == "Samsung"
        assert cp["category"] == "phone"
        assert cp["confidence"] == 1.0
        assert cp["source"] == "user_input"

    @pytest.mark.unit
    def test_empty_model_raises(self):
        with pytest.raises(ValueError, match="모델명"):
            confirm_from_user_input({}, model="")

    @pytest.mark.unit
    def test_whitespace_model_raises(self):
        with pytest.raises(ValueError, match="모델명"):
            confirm_from_user_input({}, model="   ")

    @pytest.mark.unit
    def test_missing_brand_defaults_to_unknown(self):
        data = {}
        confirm_from_user_input(data, model="테스트")
        assert data["confirmed_product"]["brand"] == "Unknown"

    @pytest.mark.unit
    def test_missing_category_defaults_to_unknown(self):
        data = {}
        confirm_from_user_input(data, model="테스트")
        assert data["confirmed_product"]["category"] == "unknown"

    @pytest.mark.unit
    def test_removes_user_input_prompt(self):
        data = {"user_input_prompt": "입력해주세요"}
        confirm_from_user_input(data, model="테스트")
        assert "user_input_prompt" not in data
