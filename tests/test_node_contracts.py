"""
노드별 state output contract 테스트.

각 노드가 실행 후 계약된 키를 반드시 state에 남기는지 검증한다.
LLM은 mock(None)하여 룰 기반 fallback 경로를 테스트한다.
"""
import sys
from unittest.mock import patch

import pytest

from app.domain.node_contracts import NODE_OUTPUT_CONTRACTS, check_contract


# ── 공통 state 팩토리 ───────────────────────────────────────────


def _make_minimal_state(**overrides):
    """최소한의 SellerCopilotState 딕셔너리."""
    state = {
        "session_id": "contract-test",
        "status": "initialized",
        "checkpoint": "",
        "schema_version": 2,
        "image_paths": ["img.jpg"],
        "selected_platforms": ["bunjang", "joongna"],
        "user_product_input": {},
        "product_candidates": [],
        "confirmed_product": None,
        "analysis_source": None,
        "needs_user_input": False,
        "clarification_prompt": None,
        "search_queries": [],
        "market_context": None,
        "strategy": None,
        "canonical_listing": None,
        "platform_packages": {},
        "rewrite_instruction": None,
        "validation_passed": False,
        "validation_result": {"passed": False, "issues": []},
        "validation_retry_count": 0,
        "tool_calls": [],
        "publish_diagnostics": [],
        "publish_retry_count": 0,
        "publish_results": {},
        "sale_status": None,
        "optimization_suggestion": None,
        "followup_due_at": None,
        "error_history": [],
        "last_error": None,
        "debug_logs": [],
        "mission_goal": "balanced",
        "plan": {},
        "plan_revision_count": 0,
        "max_replans": 1,
        "decision_rationale": [],
        "missing_information": [],
        "critic_score": 0,
        "critic_feedback": [],
        "critic_rewrite_instructions": [],
        "critic_retry_count": 0,
        "max_critic_retries": 2,
        "pre_listing_questions": [],
        "pre_listing_answers": {},
        "pre_listing_done": False,
    }
    state.update(overrides)
    return state


# ── check_contract 유틸 테스트 ──────────────────────────────────


class TestCheckContract:
    @pytest.mark.unit
    def test_unknown_node(self):
        violations = check_contract("nonexistent_node", {})
        assert any("unknown" in v for v in violations)

    @pytest.mark.unit
    def test_missing_required_key(self):
        violations = check_contract("pricing_strategy_node", {})
        assert len(violations) >= 2

    @pytest.mark.unit
    def test_passing_contract(self):
        state = {"strategy": {"goal": "balanced"}, "checkpoint": "B_strategy_complete"}
        violations = check_contract("pricing_strategy_node", state)
        assert violations == []

    @pytest.mark.unit
    def test_one_of_satisfied(self):
        state = {"checkpoint": "A_complete", "status": "product_confirmed", "confirmed_product": {"model": "x"}}
        violations = check_contract("product_identity_node", state)
        assert violations == []

    @pytest.mark.unit
    def test_one_of_not_satisfied(self):
        state = {"checkpoint": "A_complete", "status": "product_confirmed"}
        violations = check_contract("product_identity_node", state)
        assert any("one_of" in v for v in violations)


# ── 노드별 contract 검증 (integration) ─────────────────────────


class TestMissionPlannerContract:
    @pytest.mark.integration
    @patch("app.graph.nodes.planner_agent._build_react_llm", return_value=None)
    def test_rule_based_fallback_satisfies_contract(self, _mock_llm):
        from app.graph.nodes.planner_agent import mission_planner_node

        state = _make_minimal_state(
            confirmed_product={"brand": "Apple", "model": "iPhone 15", "category": "smartphone"},
        )
        result = mission_planner_node(state)
        violations = check_contract("mission_planner_node", result)
        assert violations == [], f"Contract violations: {violations}"


class TestProductIdentityContract:
    @pytest.mark.integration
    def test_user_input_path_satisfies_contract(self):
        from app.graph.nodes.product_agent import product_identity_node

        state = _make_minimal_state(
            user_product_input={"brand": "Samsung", "model": "Galaxy S24", "category": "smartphone"},
        )
        result = product_identity_node(state)
        violations = check_contract("product_identity_node", result)
        assert violations == [], f"Contract violations: {violations}"

    @pytest.mark.integration
    def test_low_confidence_path_satisfies_contract(self):
        from app.graph.nodes.product_agent import product_identity_node

        state = _make_minimal_state(
            product_candidates=[{"brand": "Unknown", "model": "unknown", "confidence": 0.3, "category": "etc"}],
        )
        result = product_identity_node(state)
        violations = check_contract("product_identity_node", result)
        assert violations == [], f"Contract violations: {violations}"


class TestPreListingClarificationContract:
    @pytest.mark.integration
    @patch("app.graph.nodes.clarification_listing_agent._build_react_llm", return_value=None)
    def test_rule_based_fallback_satisfies_contract(self, _mock_llm):
        from app.graph.nodes.clarification_listing_agent import pre_listing_clarification_node

        state = _make_minimal_state(
            confirmed_product={"brand": "Apple", "model": "iPhone 15", "category": "smartphone"},
        )
        result = pre_listing_clarification_node(state)
        violations = check_contract("pre_listing_clarification_node", result)
        assert violations == [], f"Contract violations: {violations}"


class TestMarketIntelligenceContract:
    @pytest.mark.integration
    @patch("app.graph.nodes.market_agent._build_react_llm", return_value=None)
    def test_fallback_satisfies_contract(self, _mock_llm):
        from app.graph.nodes.market_agent import market_intelligence_node

        state = _make_minimal_state(
            confirmed_product={"brand": "Apple", "model": "iPhone 15", "category": "smartphone"},
        )
        result = market_intelligence_node(state)
        violations = check_contract("market_intelligence_node", result)
        assert violations == [], f"Contract violations: {violations}"


class TestPricingStrategyContract:
    @pytest.mark.integration
    def test_satisfies_contract(self):
        from app.graph.nodes.market_agent import pricing_strategy_node

        state = _make_minimal_state(
            market_context={"median_price": 500000, "sample_count": 5},
            mission_goal="balanced",
        )
        result = pricing_strategy_node(state)
        violations = check_contract("pricing_strategy_node", result)
        assert violations == [], f"Contract violations: {violations}"

    @pytest.mark.integration
    def test_goal_propagates_to_strategy(self):
        """mission_goal이 strategy.goal로 전파되는지 검증 (M40 연계)."""
        from app.graph.nodes.market_agent import pricing_strategy_node

        for goal in ("fast_sell", "balanced", "profit_max"):
            state = _make_minimal_state(
                market_context={"median_price": 500000, "sample_count": 5},
                mission_goal=goal,
            )
            result = pricing_strategy_node(state)
            assert result["strategy"]["goal"] == goal


class TestCopywritingContract:
    @pytest.mark.integration
    def test_fallback_satisfies_contract(self):
        """PR2: copywriting은 ReAct 제거. ListingService 호출 실패 시 template fallback이
        contract를 만족하는지 검증."""
        from unittest.mock import AsyncMock as _AsyncMock
        from app.graph.nodes.copywriting_agent import copywriting_node

        state = _make_minimal_state(
            confirmed_product={"brand": "Apple", "model": "iPhone 15", "category": "smartphone"},
            market_context={"median_price": 500000, "sample_count": 5},
            strategy={"goal": "balanced", "recommended_price": 485000, "negotiation_policy": "small negotiation allowed"},
        )
        with patch("app.services.listing_service.ListingService") as MockSvc:
            MockSvc.return_value.build_canonical_listing = _AsyncMock(side_effect=Exception("LLM down"))
            result = copywriting_node(state)
        violations = check_contract("copywriting_node", result)
        assert violations == [], f"Contract violations: {violations}"


class TestListingCriticContract:
    @pytest.mark.integration
    @patch("app.graph.nodes.critic_agent._build_react_llm", return_value=None)
    def test_rule_based_fallback_satisfies_contract(self, _mock_llm):
        from app.graph.nodes.critic_agent import listing_critic_node

        state = _make_minimal_state(
            canonical_listing={
                "title": "Apple iPhone 15 Pro 256GB 판매합니다",
                "description": "깨끗하게 사용했습니다. 상태 좋습니다. 구성품 전부 있습니다. 직거래 선호합니다.",
                "price": 950000,
                "tags": ["iPhone15Pro"],
                "images": ["img.jpg"],
                "strategy": "balanced",
                "product": {"brand": "Apple", "model": "iPhone 15 Pro"},
            },
            confirmed_product={"brand": "Apple", "model": "iPhone 15 Pro", "category": "smartphone"},
            market_context={"median_price": 980000, "sample_count": 12},
            strategy={"goal": "balanced", "recommended_price": 950000},
        )
        result = listing_critic_node(state)
        violations = check_contract("listing_critic_node", result)
        assert violations == [], f"Contract violations: {violations}"


class TestValidationContract:
    @pytest.mark.integration
    def test_satisfies_contract(self):
        from app.graph.nodes.validation_agent import validation_node

        state = _make_minimal_state(
            canonical_listing={
                "title": "Apple iPhone 15 Pro 256GB",
                "description": "깨끗하게 사용했습니다. 상태 좋습니다.",
                "price": 950000,
            },
            confirmed_product={"brand": "Apple", "model": "iPhone 15 Pro", "category": "smartphone"},
            market_context={"median_price": 980000, "sample_count": 12},
        )
        result = validation_node(state)
        violations = check_contract("validation_contract" if False else "validation_node", result)
        assert violations == [], f"Contract violations: {violations}"


class TestPackageBuilderContract:
    @pytest.mark.integration
    def test_satisfies_contract(self):
        from app.graph.nodes.packaging_agent import package_builder_node

        state = _make_minimal_state(
            canonical_listing={
                "title": "Apple iPhone 15 Pro 256GB",
                "description": "깨끗하게 사용했습니다.",
                "price": 950000,
                "images": ["img.jpg"],
                "product": {"category": "smartphone"},
            },
        )
        result = package_builder_node(state)
        violations = check_contract("package_builder_node", result)
        assert violations == [], f"Contract violations: {violations}"


# ── 전체 계약 커버리지 ──────────────────────────────────────────


class TestContractCoverage:
    @pytest.mark.unit
    def test_all_contracts_have_tests(self):
        """NODE_OUTPUT_CONTRACTS에 정의된 모든 노드가 이 파일에서 테스트되는지."""
        tested_nodes = {
            "mission_planner_node",
            "product_identity_node",
            "pre_listing_clarification_node",
            "market_intelligence_node",
            "pricing_strategy_node",
            "copywriting_node",
            "listing_critic_node",
            "validation_node",
            "package_builder_node",
        }
        assert tested_nodes == set(NODE_OUTPUT_CONTRACTS.keys())
