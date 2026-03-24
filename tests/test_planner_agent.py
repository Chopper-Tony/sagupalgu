"""
Agent 0 — Mission Planner + Replan 라우팅 테스트.
"""
import pytest
from unittest.mock import patch

from app.graph.nodes.planner_agent import _rule_based_planning, mission_planner_node
from app.graph.routing import route_after_critic


# ── 룰 기반 계획 unit 테스트 ──────────────────────────────────────


class TestRuleBasedPlanning:

    @pytest.mark.unit
    def test_basic_plan_has_steps(self):
        state = {"confirmed_product": {"brand": "Apple", "model": "iPhone 15 Pro", "category": "phone"}}
        result = _rule_based_planning(state, is_replan=False)
        assert "steps" in result["plan"]
        assert len(result["plan"]["steps"]) >= 3

    @pytest.mark.unit
    def test_missing_model_detected(self):
        state = {"confirmed_product": {"brand": "Unknown"}}
        result = _rule_based_planning(state, is_replan=False)
        assert "model_name" in result["missing_information"]

    @pytest.mark.unit
    def test_low_sample_count_adds_expand_search(self):
        state = {
            "confirmed_product": {"model": "Test"},
            "market_context": {"sample_count": 1, "median_price": 100000},
        }
        result = _rule_based_planning(state, is_replan=False)
        assert "expand_market_search" in result["plan"]["steps"]

    @pytest.mark.unit
    def test_replan_with_trust_issues(self):
        state = {
            "confirmed_product": {"model": "Test"},
            "market_context": {"sample_count": 10},
            "critic_feedback": [{"type": "trust", "impact": "high", "reason": "상태 정보 부족"}],
        }
        result = _rule_based_planning(state, is_replan=True)
        assert "product_condition_details" in result["missing_information"]
        assert "rewrite_with_critic_feedback" in result["plan"]["steps"]

    @pytest.mark.unit
    def test_replan_with_seo_issues(self):
        state = {
            "confirmed_product": {"model": "Test"},
            "critic_feedback": [{"type": "seo", "impact": "medium", "reason": "키워드 부족"}],
        }
        result = _rule_based_planning(state, is_replan=True)
        assert any("검색 최적화" in r for r in result["rationale"])

    @pytest.mark.unit
    def test_goal_preserved(self):
        state = {"confirmed_product": {"model": "Test"}, "mission_goal": "fast_sell"}
        result = _rule_based_planning(state, is_replan=False)
        assert result["mission_goal"] == "fast_sell"

    @pytest.mark.unit
    def test_focus_matches_goal(self):
        for goal in ["fast_sell", "balanced", "profit_max"]:
            state = {"confirmed_product": {"model": "Test"}, "mission_goal": goal}
            result = _rule_based_planning(state, is_replan=False)
            assert result["plan"]["focus"]  # 비어있지 않아야 함


# ── Replan 라우팅 테스트 ──────────────────────────────────────────


class TestReplanRouting:

    @pytest.mark.unit
    def test_rewrite_exhausted_triggers_replan(self):
        state = {
            "critic_score": 40,
            "critic_retry_count": 2,
            "max_critic_retries": 2,
            "plan_revision_count": 0,
            "max_replans": 1,
            "rewrite_instruction": "수정해주세요",
        }
        assert route_after_critic(state) == "mission_planner_node"

    @pytest.mark.unit
    def test_replan_exhausted_forces_pass(self):
        state = {
            "critic_score": 40,
            "critic_retry_count": 2,
            "max_critic_retries": 2,
            "plan_revision_count": 1,
            "max_replans": 1,
        }
        assert route_after_critic(state) == "validation_node"

    @pytest.mark.unit
    def test_rewrite_before_replan(self):
        """rewrite 한도가 남아있으면 replan보다 rewrite 우선."""
        state = {
            "critic_score": 40,
            "critic_retry_count": 1,
            "max_critic_retries": 2,
            "plan_revision_count": 0,
            "max_replans": 1,
            "rewrite_instruction": "수정",
        }
        assert route_after_critic(state) == "copywriting_node"


# ── Planner 노드 통합 테스트 (LLM mock — CI 안정성) ──────────────


class TestMissionPlannerNode:

    @pytest.mark.integration
    def test_first_plan_creates_plan(self, base_state):
        """LLM 없이 룰 기반으로 plan이 생성된다."""
        state = {**base_state, "plan_revision_count": 0, "max_replans": 1,
                 "decision_rationale": [], "missing_information": [], "mission_goal": "balanced", "plan": {}}
        with patch("app.graph.nodes.planner_agent._build_react_llm", return_value=None):
            result = mission_planner_node(state)
        assert "steps" in result["plan"]
        assert len(result["decision_rationale"]) > 0

    @pytest.mark.integration
    def test_replan_reflects_critic_feedback(self, base_state):
        """replan 시 critic 피드백이 반영되어 missing_information이 생성된다."""
        state = {**base_state, "plan_revision_count": 1, "max_replans": 1,
                 "decision_rationale": [], "missing_information": [], "mission_goal": "balanced", "plan": {},
                 "critic_feedback": [{"type": "trust", "impact": "high", "reason": "신뢰 정보 부족"}]}
        with patch("app.graph.nodes.planner_agent._build_react_llm", return_value=None):
            result = mission_planner_node(state)
        assert "product_condition_details" in result.get("missing_information", [])

    @pytest.mark.integration
    def test_plan_has_focus(self, base_state):
        state = {**base_state, "plan_revision_count": 0, "max_replans": 1,
                 "decision_rationale": [], "missing_information": [], "mission_goal": "fast_sell", "plan": {}}
        with patch("app.graph.nodes.planner_agent._build_react_llm", return_value=None):
            result = mission_planner_node(state)
        assert result["plan"].get("focus")
