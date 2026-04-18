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
    """PR2 변경: routing은 critic이 정한 repair_action만 본다.
    replan 결정은 critic 내부(_decide_routing)에서 score·issues·retry로 한다."""

    @pytest.mark.unit
    def test_critic이_replan_결정시_planner로(self):
        state = {"repair_action": "replan", "plan_revision_count": 0}
        assert route_after_critic(state) == "mission_planner_node"

    @pytest.mark.unit
    def test_replan_상한_도달시_강제_validation(self):
        """plan_revision_count >= MAX_PLAN_REVISIONS면 critic이 replan 요청해도 강제 통과."""
        from app.domain.critic_policy import MAX_PLAN_REVISIONS

        state = {"repair_action": "replan", "plan_revision_count": MAX_PLAN_REVISIONS}
        assert route_after_critic(state) == "validation_rules_node"

    @pytest.mark.unit
    def test_critic이_rewrite_결정시_copywriting으로(self):
        state = {"repair_action": "rewrite_full"}
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


# ── PR3 신규: Strategy Agent 4 정책 필드 ────────────────────────────


class TestPlannerPolicyFields:
    """planner가 4 정책 필드를 산출하는지 (rule-based fallback 기반)."""

    @pytest.mark.integration
    def test_4_정책필드_baseline_생성(self, base_state):
        state = {**base_state, "plan_revision_count": 0, "max_replans": 1,
                 "decision_rationale": [], "missing_information": [], "mission_goal": "balanced", "plan": {}}
        with patch("app.graph.nodes.planner_agent._build_react_llm", return_value=None):
            result = mission_planner_node(state)

        assert result["plan_mode"] in {"shallow", "balanced", "deep"}
        assert result["market_depth"] in {"skip", "crawl_only", "crawl_plus_rag"}
        assert result["critic_policy"] in {"minimal", "normal", "strict"}
        assert result["clarification_policy"] in {"ask_early", "ask_late"}

    @pytest.mark.integration
    def test_정보풍부_사용자가격_있으면_skip_시도(self, base_state):
        """rule-based fallback: confirmed_product 충실 + user_price → market_depth=skip 후보."""
        state = {**base_state, "plan_revision_count": 0, "max_replans": 1,
                 "decision_rationale": [], "missing_information": [], "mission_goal": "balanced", "plan": {},
                 "user_product_input": {"price": 800000}}
        # market_context도 충분히 존재한다고 가정 (base_state)
        with patch("app.graph.nodes.planner_agent._build_react_llm", return_value=None):
            result = mission_planner_node(state)

        assert result["plan_mode"] == "shallow"
        assert result["market_depth"] == "skip"

    @pytest.mark.integration
    def test_replan시_critic_policy_강화(self, base_state):
        """replan + missing 정보 → plan_mode=deep + critic_policy strict 쪽으로."""
        state = {**base_state, "plan_revision_count": 1, "max_replans": 2,
                 "decision_rationale": [], "missing_information": [], "mission_goal": "balanced", "plan": {},
                 "critic_feedback": [{"type": "trust", "impact": "high", "reason": "신뢰 부족"}]}
        with patch("app.graph.nodes.planner_agent._build_react_llm", return_value=None):
            result = mission_planner_node(state)

        assert result["plan_mode"] == "deep"
        assert result["critic_policy"] in {"normal", "strict"}

    @pytest.mark.unit
    def test_조합_제약_위반_정규화(self, base_state):
        """LLM이 shallow + strict 같은 모순 조합 산출 시 normal로 강등."""
        state = {**base_state, "plan_revision_count": 0, "max_replans": 1,
                 "decision_rationale": [], "missing_information": [], "mission_goal": "balanced", "plan": {}}

        bad_plan = {
            "plan": {"steps": ["s1"], "focus": "x"},
            "mission_goal": "balanced",
            "rationale": ["test"],
            "missing_information": [],
            "plan_mode": "shallow",
            "market_depth": "crawl_only",
            "critic_policy": "strict",   # shallow와 충돌
            "clarification_policy": "ask_early",
        }
        with patch("app.graph.nodes.planner_agent._run_llm_planning", return_value=bad_plan):
            result = mission_planner_node(state)

        # shallow + strict는 정규화로 normal/minimal 중 하나
        from app.domain.critic_policy import POLICY_COMBO_RULES
        assert result["critic_policy"] in POLICY_COMBO_RULES["shallow"]["critic_policy"]


# ── PR3 신규: 정책 매트릭스 회귀 (8 조합) ──────────────────────────


_POLICY_MATRIX = [
    ("shallow", "crawl_only", "minimal", "ask_late"),
    ("shallow", "skip", "minimal", "ask_late"),         # skip 허용 후보
    ("balanced", "crawl_plus_rag", "normal", "ask_early"),  # baseline
    ("balanced", "crawl_only", "normal", "ask_early"),
    ("deep", "crawl_plus_rag", "strict", "ask_early"),
    ("deep", "crawl_plus_rag", "normal", "ask_early"),
    # 위반 조합 (정규화 fallback 검증)
    ("shallow", "crawl_plus_rag", "strict", "ask_early"),  # 모순 → 정규화
    ("deep", "crawl_plus_rag", "minimal", "ask_early"),    # deep+minimal 위반 → 정규화
]


class TestPolicyMatrix:
    """planner가 어떤 4정책 조합을 받아도 graph가 깨지지 않고 정규화·routing이 안전한지."""

    @pytest.mark.unit
    @pytest.mark.parametrize("plan_mode,market_depth,critic_policy,clarification_policy", _POLICY_MATRIX)
    def test_routing_dispatch_안전(self, plan_mode, market_depth, critic_policy, clarification_policy):
        """모든 정책 조합에서 route_after_planner + route_after_critic 안전 동작."""
        from app.graph.routing import route_after_critic, route_after_planner

        state = {
            "plan_mode": plan_mode,
            "market_depth": market_depth,
            "critic_policy": critic_policy,
            "clarification_policy": clarification_policy,
            "user_product_input": {"price": 100000},  # skip 허용 조건
            "confirmed_product": {"category": "clothing"},
            "plan_revision_count": 0,
            "repair_action": "pass",
        }
        # route_after_planner는 market 또는 pricing 둘 중 하나
        result1 = route_after_planner(state)
        assert result1 in {"market_intelligence_node", "pricing_rule_node"}

        # route_after_critic은 6갈래 중 하나
        result2 = route_after_critic(state)
        assert result2 in {
            "validation_rules_node", "copywriting_node", "pricing_rule_node",
            "clarification_node", "mission_planner_node",
        }
