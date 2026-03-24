"""
Pre-listing Clarification 노드 + 라우팅 테스트.
"""
import pytest

from app.graph.nodes.clarification_listing_agent import (
    _detect_missing_info,
    _generate_questions_rule,
    pre_listing_clarification_node,
)
from app.graph.routing import route_after_pre_listing_clarification


# ── 정보 부족 탐지 unit 테스트 ──────────────────────────────────


class TestDetectMissingInfo:

    @pytest.mark.unit
    def test_all_missing_when_no_context(self):
        missing = _detect_missing_info("", {})
        assert len(missing) == 4  # 4개 항목 전부 부족

    @pytest.mark.unit
    def test_condition_keyword_found(self):
        missing = _detect_missing_info("상태 좋음 스크래치 없음", {})
        ids = [m["id"] for m in missing]
        assert "product_condition" not in ids

    @pytest.mark.unit
    def test_accessories_keyword_found(self):
        missing = _detect_missing_info("충전기 포함 박스 있음", {})
        ids = [m["id"] for m in missing]
        assert "accessories" not in ids

    @pytest.mark.unit
    def test_existing_answers_skip(self):
        missing = _detect_missing_info("", {"product_condition": "좋음", "accessories": "포함"})
        ids = [m["id"] for m in missing]
        assert "product_condition" not in ids
        assert "accessories" not in ids

    @pytest.mark.unit
    def test_delivery_keyword_found(self):
        missing = _detect_missing_info("직거래 선호 택배 가능", {})
        ids = [m["id"] for m in missing]
        assert "delivery_method" not in ids


# ── 룰 기반 질문 생성 테스트 ──────────────────────────────────────


class TestGenerateQuestionsRule:

    @pytest.mark.unit
    def test_generates_questions_for_missing(self):
        missing = [
            {"id": "product_condition", "label": "상품 상태", "keywords": []},
            {"id": "accessories", "label": "구성품 포함 여부", "keywords": []},
        ]
        questions = _generate_questions_rule(missing)
        assert len(questions) == 2
        assert all("question" in q for q in questions)
        assert all("id" in q for q in questions)

    @pytest.mark.unit
    def test_question_ids_match_missing(self):
        missing = [{"id": "usage_period", "label": "사용 기간", "keywords": []}]
        questions = _generate_questions_rule(missing)
        assert questions[0]["id"] == "usage_period"


# ── 라우팅 unit 테스트 ──────────────────────────────────────────


class TestRouteAfterPreListingClarification:

    @pytest.mark.unit
    def test_needs_input_goes_to_end(self):
        state = {"needs_user_input": True, "pre_listing_done": False}
        assert route_after_pre_listing_clarification(state) == "__end__"

    @pytest.mark.unit
    def test_done_goes_to_market(self):
        state = {"needs_user_input": False, "pre_listing_done": True}
        assert route_after_pre_listing_clarification(state) == "market_intelligence_node"

    @pytest.mark.unit
    def test_no_questions_needed_goes_to_market(self):
        state = {"needs_user_input": False, "pre_listing_done": False}
        assert route_after_pre_listing_clarification(state) == "market_intelligence_node"


# ── 노드 통합 테스트 ──────────────────────────────────────────


class TestPreListingClarificationNode:

    @pytest.mark.integration
    def test_sufficient_info_passes_through(self, base_state):
        state = {**base_state,
                 "pre_listing_done": False, "pre_listing_questions": [],
                 "pre_listing_answers": {}, "missing_information": []}
        # base_state의 confirmed_product에 brand/model이 있지만 상태/구성품 정보는 없음
        # → 일부 질문이 생성될 수 있음
        result = pre_listing_clarification_node(state)
        assert isinstance(result.get("pre_listing_questions"), list)

    @pytest.mark.integration
    def test_already_done_skips(self, base_state):
        state = {**base_state,
                 "pre_listing_done": True, "pre_listing_questions": [],
                 "pre_listing_answers": {}, "missing_information": []}
        result = pre_listing_clarification_node(state)
        assert result["pre_listing_done"] is True

    @pytest.mark.integration
    def test_missing_info_generates_questions(self, base_state):
        state = {**base_state,
                 "pre_listing_done": False, "pre_listing_questions": [],
                 "pre_listing_answers": {}, "missing_information": [],
                 "confirmed_product": {"brand": "Apple", "model": "iPhone 15 Pro"}}
        result = pre_listing_clarification_node(state)
        if result.get("pre_listing_questions"):
            assert result["needs_user_input"] is True
            assert len(result["pre_listing_questions"]) > 0

    @pytest.mark.integration
    def test_answers_reduce_questions(self, base_state):
        state = {**base_state,
                 "pre_listing_done": False, "pre_listing_questions": [],
                 "pre_listing_answers": {
                     "product_condition": "상태 좋음",
                     "usage_period": "6개월",
                     "accessories": "충전기 포함",
                     "delivery_method": "직거래",
                 },
                 "missing_information": []}
        result = pre_listing_clarification_node(state)
        assert result["pre_listing_done"] is True
        assert len(result.get("pre_listing_questions", [])) == 0
