"""
Agent 6 — Listing Critic 에이전트 + routing 테스트.

critic_score에 따라 pass/rewrite 분기가 올바르게 동작하는지 검증.
통합 테스트는 LLM을 mock해서 CI에서 결정론적으로 동작.
"""
import pytest
from unittest.mock import patch

from app.graph.nodes.critic_agent import _rule_based_critique, listing_critic_node
from app.graph.routing import route_after_critic


# ── 룰 기반 비평 unit 테스트 ──────────────────────────────────────


class TestRuleBasedCritique:

    @pytest.mark.unit
    def test_good_listing_high_score(self):
        listing = {
            "title": "Apple iPhone 15 Pro 256GB 판매합니다",
            "description": "배터리 상태 좋고 구성품 전부 있습니다. 직거래 선호하며 택배도 가능합니다. 사용 기간 6개월.",
            "price": 900000,
            "tags": ["iPhone", "Apple"],
        }
        product = {"brand": "Apple", "model": "iPhone 15 Pro", "category": "smartphone"}
        market = {"median_price": 950000}

        result = _rule_based_critique(listing, product, market)
        assert result["score"] >= 70
        assert isinstance(result["issues"], list)

    @pytest.mark.unit
    def test_short_title_low_score(self):
        listing = {"title": "팝니다", "description": "짧음", "price": 100, "tags": []}
        product = {"model": "iPhone 15 Pro"}
        market = {"median_price": 900000}

        result = _rule_based_critique(listing, product, market)
        assert result["score"] < 70
        assert any(i["type"] == "title" for i in result["issues"])

    @pytest.mark.unit
    def test_missing_model_in_title(self):
        listing = {
            "title": "중고폰 판매합니다 상태 좋음",
            "description": "상태 좋고 배터리 건강합니다. 직거래 가능합니다. 구성품 포함.",
            "price": 900000,
        }
        product = {"model": "Galaxy S24"}
        market = {"median_price": 900000}

        result = _rule_based_critique(listing, product, market)
        assert any(i["type"] == "seo" for i in result["issues"])

    @pytest.mark.unit
    def test_zero_price_penalty(self):
        listing = {"title": "Samsung Galaxy S24 판매합니다", "description": "상태 좋습니다 직거래 가능", "price": 0}
        product = {"model": "Galaxy S24"}
        market = {"median_price": 800000}

        result = _rule_based_critique(listing, product, market)
        assert any(i["type"] == "price" for i in result["issues"])

    @pytest.mark.unit
    def test_no_trust_info_penalty(self):
        listing = {
            "title": "iPhone 15 Pro 판매합니다 좋은 가격",
            "description": "좋은 가격에 드립니다. 빠른 거래 원합니다.",
            "price": 900000,
        }
        product = {"model": "iPhone 15 Pro"}
        market = {"median_price": 900000}

        result = _rule_based_critique(listing, product, market)
        assert any(i["type"] == "trust" for i in result["issues"])

    @pytest.mark.unit
    def test_rewrite_instructions_generated(self):
        listing = {"title": "팝니다", "description": "짧음", "price": 0, "tags": []}
        product = {"model": "Test"}
        market = {"median_price": 100000}

        result = _rule_based_critique(listing, product, market)
        assert len(result["rewrite_instructions"]) > 0


# ── 라우팅 unit 테스트 (PR2: repair_action 기반) ──────────────────


class TestRouteAfterCritic:
    """PR2 변경: routing은 score를 안 보고 repair_action만 dispatch.
    critic이 정한 repair_action을 받아 노드 이름으로 매핑하는지 검증."""

    @pytest.mark.unit
    def test_pass_validation으로(self):
        state = {"repair_action": "pass"}
        assert route_after_critic(state) == "validation_rules_node"

    @pytest.mark.unit
    def test_rewrite_full_copywriting으로(self):
        state = {"repair_action": "rewrite_full"}
        assert route_after_critic(state) == "copywriting_node"

    @pytest.mark.unit
    def test_rewrite_title_copywriting으로(self):
        state = {"repair_action": "rewrite_title"}
        assert route_after_critic(state) == "copywriting_node"

    @pytest.mark.unit
    def test_rewrite_description_copywriting으로(self):
        state = {"repair_action": "rewrite_description"}
        assert route_after_critic(state) == "copywriting_node"

    @pytest.mark.unit
    def test_reprice_pricing으로(self):
        state = {"repair_action": "reprice"}
        assert route_after_critic(state) == "pricing_rule_node"

    @pytest.mark.unit
    def test_clarify_clarification으로(self):
        state = {"repair_action": "clarify"}
        assert route_after_critic(state) == "clarification_node"

    @pytest.mark.unit
    def test_replan_planner으로(self):
        state = {"repair_action": "replan", "plan_revision_count": 0}
        assert route_after_critic(state) == "mission_planner_node"

    @pytest.mark.unit
    def test_repair_action_없으면_pass_default(self):
        """critic이 한 번도 안 돌았으면 repair_action 기본값 'pass' 덕에 validation으로."""
        assert route_after_critic({}) == "validation_rules_node"


# ── Critic 노드 통합 테스트 ──────────────────────────────────────


class TestListingCriticNode:

    @pytest.mark.integration
    def test_good_listing_has_score(self, base_state):
        """좋은 판매글이면 점수가 부여되고 feedback이 생성된다."""
        state = {**base_state}
        state["canonical_listing"] = {
            "title": "Apple iPhone 15 Pro 256GB 판매합니다",
            "description": "배터리 상태 좋고 구성품 전부 포함. 직거래 선호. 사용 6개월. 택배 가능합니다.",
            "price": 900000,
            "tags": ["iPhone", "Apple"],
            "images": ["img.jpg"],
            "strategy": "fast_sell",
            "product": base_state["confirmed_product"],
        }
        state["market_context"] = {"median_price": 950000}
        state["critic_retry_count"] = 0
        state["max_critic_retries"] = 2

        with patch("app.graph.nodes.critic_agent._build_react_llm", return_value=None):
            result = listing_critic_node(state)
        assert isinstance(result["critic_score"], int)
        assert result["critic_score"] > 0
        assert isinstance(result["critic_feedback"], list)

    @pytest.mark.integration
    def test_bad_listing_triggers_rewrite(self, base_state):
        """PR2: critic이 명시적으로 rewrite_full을 결정하면 critic_retry_count 증가 + rewrite_instruction 채워짐."""
        state = {**base_state}
        state["canonical_listing"] = {
            "title": "팝니다", "description": "짧음", "price": 0,
            "tags": [], "images": [], "strategy": "fast_sell", "product": {},
        }
        state["market_context"] = {"median_price": 900000}
        state["critic_retry_count"] = 0
        state["max_critic_retries"] = 2

        critique = {
            "score": 30,
            "issues": [
                {"type": "title", "impact": "high", "reason": "약함"},
                {"type": "description", "impact": "high", "reason": "짧음"},
            ],
            "rewrite_instructions": ["제목 강화", "설명 보강"],
            "repair_action": "rewrite_full",
            "failure_mode": "general_quality",
            "rewrite_plan": {"target": "full", "instruction": "전반적 보강"},
        }
        with patch("app.graph.nodes.critic_agent._run_llm_critique", return_value=critique):
            result = listing_critic_node(state)
        assert result["critic_score"] < 70
        assert result["repair_action"] == "rewrite_full"
        assert result["critic_retry_count"] == 1
        assert result.get("rewrite_instruction") is not None

    @pytest.mark.integration
    def test_missing_listing_scores_zero(self, base_state):
        state = {**base_state}
        state["canonical_listing"] = None
        state["critic_retry_count"] = 0
        state["max_critic_retries"] = 2

        with patch("app.graph.nodes.critic_agent._build_react_llm", return_value=None):
            result = listing_critic_node(state)
        assert result["critic_score"] == 0

    @pytest.mark.integration
    def test_max_retries_forces_pass(self, base_state):
        """PR2: critic_retry_count >= max → critic이 직접 repair_action='pass' + failure_mode 결정.
        LLM이 rewrite_full을 요청해도 한도 초과면 강제 pass로 빠짐."""
        state = {**base_state}
        state["canonical_listing"] = {
            "title": "팝니다", "description": "짧음", "price": 0,
            "tags": [], "images": [], "strategy": "fast_sell", "product": {},
        }
        state["market_context"] = {"median_price": 900000}
        state["critic_retry_count"] = 2
        state["max_critic_retries"] = 2

        critique = {
            "score": 30,
            "issues": [{"type": "title", "impact": "high", "reason": "약함"}],
            "rewrite_instructions": ["제목 강화"],
            "repair_action": "rewrite_full",
            "failure_mode": "general_quality",
            "rewrite_plan": {"target": "full", "instruction": "재작성"},
        }
        with patch("app.graph.nodes.critic_agent._run_llm_critique", return_value=critique):
            result = listing_critic_node(state)
        # max retries 도달 → 강제 pass + failure_mode 기록
        assert result["repair_action"] == "pass"
        assert result["failure_mode"] == "max_critic_retries_reached"


# ── PR2 신규: parse_error fallback (failure_mode 추적) ──────────────


class TestParseErrorFallback:
    """LLM 응답 파싱 실패 시 'critic_parse_error' failure_mode + safety net."""

    @pytest.mark.integration
    def test_parse_error_failure_mode_기록(self, base_state):
        state = {**base_state}
        state["canonical_listing"] = {
            "title": "Apple iPhone 15 Pro 256GB",
            "description": "정상 상태입니다. 직거래 가능. 구성품 포함. 사용 6개월.",
            "price": 900000, "tags": [], "images": [],
            "strategy": "fast_sell", "product": {},
        }
        state["market_context"] = {"median_price": 900000}

        # _run_llm_critique이 파싱 실패 (None 반환) — _build_react_llm를 None으로 막아도 같은 결과지만
        # 명시적으로 _run_llm_critique 자체를 None 반환으로 mock
        with patch("app.graph.nodes.critic_agent._run_llm_critique", return_value=None):
            result = listing_critic_node(state)

        assert result["failure_mode"] == "critic_parse_error"
        assert result["repair_action"] == "pass"
        assert any("critic_parse_error" in log for log in result.get("debug_logs", []))

    @pytest.mark.integration
    def test_parse_error도_score_관측용은_채워짐(self, base_state):
        """rule-based critique fallback이 score를 채워서 UI/workflow_meta 호환 유지."""
        state = {**base_state}
        state["canonical_listing"] = {
            "title": "Apple iPhone 15 Pro 256GB 판매합니다",
            "description": "정상 상태. 직거래 가능. 구성품 포함. 사용 6개월. 택배 가능.",
            "price": 900000, "tags": [], "images": [],
            "strategy": "fast_sell", "product": base_state.get("confirmed_product", {}),
        }
        state["market_context"] = {"median_price": 900000}

        with patch("app.graph.nodes.critic_agent._run_llm_critique", return_value=None):
            result = listing_critic_node(state)

        assert isinstance(result["critic_score"], int)
        assert result["critic_score"] >= 0


# ── PR2 신규: critic의 repair_action 결정 로직 ──────────────────────


class TestCriticDecidesRepairAction:
    """LLM이 명시적으로 repair_action을 반환하면 신뢰. 미반환 시 issues로 추론."""

    @pytest.mark.integration
    def test_LLM이_명시한_repair_action_신뢰(self, base_state):
        state = {**base_state}
        state["canonical_listing"] = {
            "title": "Apple iPhone 15 Pro 256GB 판매합니다",
            "description": "정상 상태. 직거래 가능. 구성품 포함. 사용 6개월. 택배 가능.",
            "price": 900000, "tags": [], "images": [],
            "strategy": "fast_sell", "product": {},
        }
        state["market_context"] = {"median_price": 900000}

        critique = {
            "score": 60,
            "issues": [{"type": "title", "impact": "high", "reason": "약함"}],
            "rewrite_instructions": ["제목 강화"],
            "repair_action": "rewrite_title",
            "failure_mode": "title_weak",
            "rewrite_plan": {"target": "title", "instruction": "제목에 모델명 강조"},
        }
        with patch("app.graph.nodes.critic_agent._run_llm_critique", return_value=critique):
            result = listing_critic_node(state)

        assert result["repair_action"] == "rewrite_title"
        assert result["failure_mode"] == "title_weak"
        assert result["rewrite_plan"]["target"] == "title"

    @pytest.mark.integration
    def test_가격_단독_문제_reprice_추론(self, base_state):
        """LLM이 repair_action 미반환, 가격 issue만 있으면 reprice로 추론."""
        state = {**base_state}
        state["canonical_listing"] = {
            "title": "Apple iPhone 15 Pro 256GB 판매합니다",
            "description": "정상 상태. 직거래 가능. 구성품 포함. 사용 6개월.",
            "price": 1500000, "tags": [], "images": [],
            "strategy": "fast_sell", "product": {},
        }
        state["market_context"] = {"median_price": 900000}

        critique = {
            "score": 60,
            "issues": [{"type": "price", "impact": "high", "reason": "시세 대비 60% 높음"}],
            "rewrite_instructions": ["가격 인하 검토"],
        }
        with patch("app.graph.nodes.critic_agent._run_llm_critique", return_value=critique):
            result = listing_critic_node(state)

        assert result["repair_action"] == "reprice"
        assert result["failure_mode"] == "price_off"
