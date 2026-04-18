"""
그래프 라우터 함수 단위 테스트 — langgraph 의존성 없음.

PR2 변경 반영:
  - refinement 분기 제거: route_after_validation은 항상 package_builder_node 직진
    (validation 내부에서 자동 보강)
  - critic 단순 dispatch: route_after_critic이 score 임계값이 아니라 repair_action을 본다

@pytest.mark.unit — 외부 의존성 없이 0.1초 이내 완료.
"""
from __future__ import annotations

import pytest

from app.domain.critic_policy import MAX_PLAN_REVISIONS

pytestmark = pytest.mark.unit


class TestRouteAfterProductIdentity:

    def test_needs_user_input_clarification으로_분기(self):
        from app.graph.routing import route_after_product_identity

        state = {"needs_user_input": True}
        assert route_after_product_identity(state) == "clarification_node"

    def test_confirmed_product_pre_listing으로_분기(self):
        from app.graph.routing import route_after_product_identity

        state = {"needs_user_input": False}
        assert route_after_product_identity(state) == "pre_listing_clarification_node"

    def test_빈_state도_pre_listing(self):
        from app.graph.routing import route_after_product_identity

        assert route_after_product_identity({}) == "pre_listing_clarification_node"

    def test_truthy_값도_clarification(self):
        from app.graph.routing import route_after_product_identity

        assert route_after_product_identity({"needs_user_input": 1}) == "clarification_node"


class TestRouteAfterValidation:
    """PR2 변경: refinement 제거 → 항상 package_builder_node로 직진 (보강은 validation 내부)."""

    def test_passed_True_package(self):
        from app.graph.routing import route_after_validation

        assert route_after_validation({"validation_passed": True, "validation_retry_count": 0}) == "package_builder_node"

    def test_passed_False도_package_직진_PR2(self):
        """PR2: refinement 노드 제거. validation 실패 시에도 외부 분기 없이 package로
        (보강은 validation 내부에서 처리하고, repair_action_hint만 남김)."""
        from app.graph.routing import route_after_validation

        assert route_after_validation({"validation_passed": False, "validation_retry_count": 0}) == "package_builder_node"

    def test_retry_count_무관_항상_package(self):
        from app.graph.routing import route_after_validation

        assert route_after_validation({"validation_passed": False, "validation_retry_count": 5}) == "package_builder_node"


class TestRouteAfterCriticDispatch:
    """PR2: critic이 정한 repair_action을 단순 dispatch (6갈래)."""

    def test_pass_validation으로(self):
        from app.graph.routing import route_after_critic

        assert route_after_critic({"repair_action": "pass"}) == "validation_node"

    def test_rewrite_title_copywriting으로(self):
        from app.graph.routing import route_after_critic

        assert route_after_critic({"repair_action": "rewrite_title"}) == "copywriting_node"

    def test_rewrite_description_copywriting으로(self):
        from app.graph.routing import route_after_critic

        assert route_after_critic({"repair_action": "rewrite_description"}) == "copywriting_node"

    def test_rewrite_full_copywriting으로(self):
        from app.graph.routing import route_after_critic

        assert route_after_critic({"repair_action": "rewrite_full"}) == "copywriting_node"

    def test_reprice_pricing으로(self):
        from app.graph.routing import route_after_critic

        assert route_after_critic({"repair_action": "reprice"}) == "pricing_strategy_node"

    def test_clarify_clarification으로(self):
        from app.graph.routing import route_after_critic

        assert route_after_critic({"repair_action": "clarify"}) == "clarification_node"

    def test_replan_planner으로(self):
        from app.graph.routing import route_after_critic

        state = {"repair_action": "replan", "plan_revision_count": 0}
        assert route_after_critic(state) == "mission_planner_node"

    def test_unknown_action도_validation_safety_net(self):
        from app.graph.routing import route_after_critic

        assert route_after_critic({"repair_action": "weird_action"}) == "validation_node"

    def test_repair_action_없으면_pass_default(self):
        """critic이 한 번도 안 돌았으면 repair_action 기본값 'pass' 덕에 validation으로."""
        from app.graph.routing import route_after_critic

        assert route_after_critic({}) == "validation_node"


class TestReplanLimitGuard:
    """PR2: replan 무한 루프 차단 — plan_revision_count >= MAX_PLAN_REVISIONS 시 강제 통과."""

    def test_replan_상한_도달시_강제_validation(self):
        from app.graph.routing import route_after_critic

        state = {"repair_action": "replan", "plan_revision_count": MAX_PLAN_REVISIONS}
        assert route_after_critic(state) == "validation_node"

    def test_replan_상한_도달시_failure_mode_기록(self):
        from app.graph.routing import route_after_critic

        state = {"repair_action": "replan", "plan_revision_count": MAX_PLAN_REVISIONS}
        route_after_critic(state)
        assert state["failure_mode"] == "replan_limit_reached"

    def test_replan_상한_도달시_debug_log_기록(self):
        from app.graph.routing import route_after_critic

        state = {"repair_action": "replan", "plan_revision_count": MAX_PLAN_REVISIONS}
        route_after_critic(state)
        assert any("replan_limit_reached" in log for log in state.get("debug_logs", []))

    def test_replan_상한_미만이면_planner로(self):
        from app.graph.routing import route_after_critic

        state = {"repair_action": "replan", "plan_revision_count": MAX_PLAN_REVISIONS - 1}
        assert route_after_critic(state) == "mission_planner_node"


class TestRouteAfterPreListingClarification:

    def test_정보_부족_END(self):
        from app.graph.routing import route_after_pre_listing_clarification

        state = {"needs_user_input": True, "pre_listing_done": False}
        assert route_after_pre_listing_clarification(state) == "__end__"

    def test_정보_충분_market로(self):
        from app.graph.routing import route_after_pre_listing_clarification

        state = {"pre_listing_done": True}
        assert route_after_pre_listing_clarification(state) == "market_intelligence_node"

    def test_정보_충분_skip_허용_pricing으로(self):
        """PR3: pre_listing 후 skip 허용 조건 충족 시 pricing으로 직진."""
        from app.graph.routing import route_after_pre_listing_clarification

        state = {
            "pre_listing_done": True,
            "market_depth": "skip",
            "user_product_input": {"price": 500000},
        }
        assert route_after_pre_listing_clarification(state) == "pricing_strategy_node"


# ── PR3 신규: route_after_planner + _skip_allowed 가드 ───────────────


class TestRouteAfterPlannerSkipGuard:
    """market_depth='skip' 가드 — 4 조건."""

    def test_skip_아니면_market(self):
        from app.graph.routing import route_after_planner

        assert route_after_planner({"market_depth": "crawl_plus_rag"}) == "market_intelligence_node"
        assert route_after_planner({"market_depth": "crawl_only"}) == "market_intelligence_node"

    def test_skip_사용자가격_있으면_pricing(self):
        """조건 1: user_product_input.price."""
        from app.graph.routing import route_after_planner

        state = {"market_depth": "skip", "user_product_input": {"price": 500000}}
        assert route_after_planner(state) == "pricing_strategy_node"

    def test_skip_이전_market_context_있으면_pricing(self):
        """조건 2: replan 케이스 — market_context 잔존."""
        from app.graph.routing import route_after_planner

        state = {"market_depth": "skip", "market_context": {"sample_count": 5, "median_price": 500000}}
        assert route_after_planner(state) == "pricing_strategy_node"

    def test_skip_shallow_저위험_카테고리_pricing(self):
        """조건 3: plan_mode=shallow + LOW_RISK_SKIP_CATEGORIES."""
        from app.graph.routing import route_after_planner

        state = {
            "market_depth": "skip",
            "plan_mode": "shallow",
            "confirmed_product": {"category": "clothing"},
        }
        assert route_after_planner(state) == "pricing_strategy_node"

    def test_skip_미충족_silent_crawl_only_fallback(self):
        """모든 조건 미충족 → silent crawl_only 강등 + skip_rejected_reason 기록."""
        from app.graph.routing import route_after_planner

        state = {
            "market_depth": "skip",
            "plan_mode": "deep",
            "confirmed_product": {"category": "electronics"},
        }
        result = route_after_planner(state)
        assert result == "market_intelligence_node"
        assert state["market_depth"] == "crawl_only"
        assert state["skip_rejected_reason"]
        assert any("skip_rejected" in log for log in state.get("debug_logs", []))

    def test_skip_허용시_debug_log_기록(self):
        from app.graph.routing import route_after_planner

        state = {"market_depth": "skip", "user_product_input": {"price": 100000}}
        route_after_planner(state)
        assert any("skip_allowed" in log for log in state.get("debug_logs", []))

    def test_skip_미시도시_skip_attempted_False(self):
        """CTO PR3 #2: market_depth != 'skip'이면 skip_attempted는 default False 유지."""
        from app.graph.routing import route_after_planner

        state = {"market_depth": "crawl_plus_rag"}
        route_after_planner(state)
        assert not state.get("skip_attempted", False)

    def test_skip_시도_허용시_skip_attempted_True(self):
        """CTO PR3 #2: skip 시도하면 (허용/거절 무관) skip_attempted=True."""
        from app.graph.routing import route_after_planner

        state = {"market_depth": "skip", "user_product_input": {"price": 100000}}
        route_after_planner(state)
        assert state["skip_attempted"] is True

    def test_skip_시도_거절시에도_skip_attempted_True(self):
        """CTO PR3 #2: 시도 안 함 vs 시도+거절 구분."""
        from app.graph.routing import route_after_planner

        state = {"market_depth": "skip", "plan_mode": "deep",
                 "confirmed_product": {"category": "electronics"}}
        route_after_planner(state)
        assert state["skip_attempted"] is True
        assert state["skip_rejected_reason"]
