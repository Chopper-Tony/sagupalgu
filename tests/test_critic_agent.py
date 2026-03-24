"""
Agent 6 — Listing Critic 에이전트 + routing 테스트.

critic_score에 따라 pass/rewrite 분기가 올바르게 동작하는지 검증.
"""
import pytest

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


# ── 라우팅 unit 테스트 ──────────────────────────────────────────


class TestRouteAfterCritic:

    @pytest.mark.unit
    def test_high_score_passes(self):
        state = {"critic_score": 85, "critic_retry_count": 0, "max_critic_retries": 2}
        assert route_after_critic(state) == "validation_node"

    @pytest.mark.unit
    def test_low_score_with_rewrite_instruction(self):
        state = {
            "critic_score": 50,
            "critic_retry_count": 0,
            "max_critic_retries": 2,
            "rewrite_instruction": "제목에 모델명 추가",
        }
        assert route_after_critic(state) == "copywriting_node"

    @pytest.mark.unit
    def test_low_score_max_retries_reached(self):
        state = {
            "critic_score": 50,
            "critic_retry_count": 2,
            "max_critic_retries": 2,
            "rewrite_instruction": "수정 지시",
        }
        assert route_after_critic(state) == "validation_node"

    @pytest.mark.unit
    def test_low_score_no_rewrite_instruction(self):
        state = {"critic_score": 50, "critic_retry_count": 0, "max_critic_retries": 2}
        assert route_after_critic(state) == "validation_node"

    @pytest.mark.unit
    def test_zero_score_first_retry(self):
        state = {
            "critic_score": 0,
            "critic_retry_count": 0,
            "max_critic_retries": 2,
            "rewrite_instruction": "전면 재작성",
        }
        assert route_after_critic(state) == "copywriting_node"


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

        result = listing_critic_node(state)
        assert isinstance(result["critic_score"], int)
        assert result["critic_score"] > 0
        assert isinstance(result["critic_feedback"], list)

    @pytest.mark.integration
    def test_bad_listing_triggers_rewrite(self, base_state):
        state = {**base_state}
        state["canonical_listing"] = {
            "title": "팝니다",
            "description": "짧음",
            "price": 0,
            "tags": [],
            "images": [],
            "strategy": "fast_sell",
            "product": {},
        }
        state["market_context"] = {"median_price": 900000}
        state["critic_retry_count"] = 0
        state["max_critic_retries"] = 2

        result = listing_critic_node(state)
        assert result["critic_score"] < 70
        assert result["critic_retry_count"] == 1
        assert result.get("rewrite_instruction") is not None

    @pytest.mark.integration
    def test_missing_listing_scores_zero(self, base_state):
        state = {**base_state}
        state["canonical_listing"] = None
        state["critic_retry_count"] = 0
        state["max_critic_retries"] = 2

        result = listing_critic_node(state)
        assert result["critic_score"] == 0

    @pytest.mark.integration
    def test_max_retries_stops_rewrite(self, base_state):
        state = {**base_state}
        state["canonical_listing"] = {
            "title": "팝니다", "description": "짧음", "price": 0,
            "tags": [], "images": [], "strategy": "fast_sell", "product": {},
        }
        state["market_context"] = {"median_price": 900000}
        state["critic_retry_count"] = 2
        state["max_critic_retries"] = 2

        result = listing_critic_node(state)
        # max retries 도달 → rewrite_instruction 설정하지 않아야 함
        assert result["critic_retry_count"] == 2  # 증가하지 않음
