"""
에이전트 3 (판매글 생성, Single Tool Node) + 에이전트 4 (검증, Deterministic) 테스트.

PR2 변경 반영:
  - copywriting_node가 ReAct → 단일 LLM 호출로 강등 (state.rewrite_plan으로 분기)
  - refinement_node가 validation_node에 흡수 → copywriting의 refinement_node는 deprecated no-op
  - validation_node가 자동 보강 + 재검증 흡수 (description 짧음/price 0원 한정)
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch

pytestmark = pytest.mark.integration


# ─────────────────────────────────────────────────────────────────
# 에이전트 3: copywriting (Single Tool Node) — rewrite_plan 분기
# ─────────────────────────────────────────────────────────────────

class TestCopywritingDispatch:
    """PR2 핵심: state.rewrite_plan으로 generate vs rewrite 분기 (3케이스)."""

    def test_신규_generate(self, base_state):
        """rewrite_plan 없음 + canonical_listing 없음 → ListingService.build_canonical_listing."""
        from app.graph.seller_copilot_nodes import copywriting_node

        state = {**base_state, "canonical_listing": None, "rewrite_instruction": None, "rewrite_plan": {}}
        new_listing = {
            "title": "신규 생성 제목", "description": "신규 설명. 직거래 가능. 구성품 포함.",
            "price": 950000, "tags": [], "images": [],
        }

        with patch("app.services.listing_service.ListingService") as MockSvc:
            instance = MockSvc.return_value
            instance.build_canonical_listing = AsyncMock(return_value=new_listing)
            result = copywriting_node(state)

        assert result["status"] == "draft_generated"
        assert result["canonical_listing"]["title"] == "신규 생성 제목"

    def test_rewrite_title_분기(self, base_state):
        """rewrite_plan.target='title' → ListingService.rewrite_listing 호출 + 'title만' 컨텍스트."""
        from app.graph.seller_copilot_nodes import copywriting_node

        existing = {**base_state["canonical_listing"], "title": "약한 제목"}
        rewritten = {**existing, "title": "Apple iPhone 15 Pro 256GB 판매합니다 신뢰감 보장"}
        state = {
            **base_state,
            "canonical_listing": existing,
            "rewrite_plan": {"target": "title", "instruction": "제목에 모델명 + 신뢰감"},
        }

        with patch("app.services.listing_service.ListingService") as MockSvc:
            instance = MockSvc.return_value
            instance.rewrite_listing = AsyncMock(return_value=rewritten)
            result = copywriting_node(state)

        assert result["canonical_listing"]["title"] == rewritten["title"]
        # rewrite 실행 후 정리
        assert result["rewrite_plan"] == {}
        # rewrite_listing 호출 시 instruction에 [제목만 재작성] 컨텍스트가 붙어야 함
        called_instruction = instance.rewrite_listing.call_args.kwargs["rewrite_instruction"]
        assert "[제목만 재작성]" in called_instruction

    def test_rewrite_full_분기(self, base_state):
        """rewrite_plan.target='full' → ListingService.rewrite_listing + '전체 재작성' 컨텍스트."""
        from app.graph.seller_copilot_nodes import copywriting_node

        existing = {**base_state["canonical_listing"], "title": "약한 제목", "description": "짧음"}
        rewritten = {**existing, "title": "강화된 제목", "description": "강화된 설명입니다. 직거래 가능. 구성품 포함."}
        state = {
            **base_state,
            "canonical_listing": existing,
            "rewrite_plan": {"target": "full", "instruction": "전반적 강화"},
        }

        with patch("app.services.listing_service.ListingService") as MockSvc:
            instance = MockSvc.return_value
            instance.rewrite_listing = AsyncMock(return_value=rewritten)
            result = copywriting_node(state)

        assert result["canonical_listing"]["title"] == "강화된 제목"
        called_instruction = instance.rewrite_listing.call_args.kwargs["rewrite_instruction"]
        assert "[전체 재작성]" in called_instruction


class TestCopywritingFallbackChain:
    """단일 LLM 호출 실패 → 결정론적 fallback 체인 (rule-based → template)."""

    def test_llm_실패시_template_fallback(self, base_state):
        """ListingService 호출 자체가 실패하고 rewrite도 없으면 template로."""
        from app.graph.seller_copilot_nodes import copywriting_node

        state = {**base_state, "canonical_listing": None, "rewrite_instruction": None}

        with patch("app.services.listing_service.ListingService") as MockSvc:
            MockSvc.return_value.build_canonical_listing = AsyncMock(side_effect=Exception("LLM down"))
            result = copywriting_node(state)

        assert result["canonical_listing"] is not None
        assert result["status"] == "draft_generated"

    def test_rewrite_llm_실패시_규칙기반_반영(self, base_state):
        """rewrite_plan 있음 + LLM 실패 → _apply_rewrite_instruction_rule_based로 가격 추출."""
        from app.graph.seller_copilot_nodes import copywriting_node

        existing = {**base_state["canonical_listing"], "title": "기존 제목", "description": "기존 설명"}
        state = {
            **base_state,
            "canonical_listing": existing,
            "rewrite_plan": {"target": "full", "instruction": "가격을 500,000원으로 낮춰주세요"},
        }

        with patch("app.services.listing_service.ListingService") as MockSvc:
            MockSvc.return_value.rewrite_listing = AsyncMock(side_effect=Exception("서비스 장애"))
            result = copywriting_node(state)

        listing = result["canonical_listing"]
        assert listing["price"] == 500000
        assert "500,000원" in listing["description"]
        assert result["rewrite_plan"] == {}

    def test_rewrite_모든_fallback_실패시_기존_listing_보존(self, base_state):
        """rule-based도 instruction을 description에 append하므로 기존 title은 유지된다."""
        from app.graph.seller_copilot_nodes import copywriting_node

        existing = {**base_state["canonical_listing"], "title": "기존 제목", "description": "기존 설명"}
        state = {
            **base_state,
            "canonical_listing": existing,
            "rewrite_plan": {"target": "full", "instruction": "더 매력적으로"},
        }

        with patch("app.services.listing_service.ListingService") as MockSvc:
            MockSvc.return_value.rewrite_listing = AsyncMock(side_effect=Exception("장애"))
            result = copywriting_node(state)

        assert result["canonical_listing"]["title"] == "기존 제목"
        assert "더 매력적으로" in result["canonical_listing"]["description"]

    def test_apply_rewrite_instruction_rule_based(self, base_state):
        """규칙 기반 재작성 함수 단위 테스트 (가격 인하 지시)."""
        from app.graph.nodes.copywriting_agent import _apply_rewrite_instruction_rule_based

        existing = {**base_state["canonical_listing"], "description": "좋은 상품입니다"}
        product = base_state["confirmed_product"]
        strategy = base_state["strategy"]

        result = _apply_rewrite_instruction_rule_based(
            existing, "가격을 300,000원으로 인하해주세요", product, strategy,
        )
        assert result["price"] == 300000
        assert "300,000원" in result["description"]


# PR4-cleanup: TestRefinementDeprecated 제거.
#   refinement_node는 PR2에서 validation_rules_node에 흡수되었고,
#   PR4-cleanup에서 deprecated wrapper가 완전히 제거됨.
#   validation 자동 보강 동작은 TestValidationAgent에서 검증함.


# ─────────────────────────────────────────────────────────────────
# 에이전트 4: validation (Deterministic Node) — refinement 흡수
# ─────────────────────────────────────────────────────────────────

class TestValidationAgent:

    def test_정상_listing_통과(self, base_state):
        from app.graph.seller_copilot_nodes import validation_rules_node

        result = validation_rules_node(base_state)
        assert result["validation_passed"] is True
        assert result["checkpoint"] == "B_complete"

    def test_짧은제목_실패_보강불가(self, base_state):
        """title은 자동 보강 불가 → repair_action_hint='rewrite_title' 남김."""
        from app.graph.seller_copilot_nodes import validation_rules_node

        state = {**base_state}
        state["canonical_listing"] = {**base_state["canonical_listing"], "title": "짧"}
        result = validation_rules_node(state)

        assert result["validation_passed"] is False
        error_codes = [i["code"] for i in result["validation_result"]["issues"]]
        assert "title_too_short" in error_codes
        assert result["repair_action_hint"] == "rewrite_title"

    def test_짧은설명_자동_보강_후_pass(self, base_state):
        """description 짧음은 자동 보강 가능 → 보강 후 재검증 → pass."""
        from app.graph.seller_copilot_nodes import validation_rules_node

        state = {**base_state}
        state["canonical_listing"] = {**base_state["canonical_listing"], "description": "짧음"}
        result = validation_rules_node(state)

        assert result["validation_passed"] is True
        # 보강 후 description 길이 충족
        assert len(result["canonical_listing"]["description"]) >= 20
        assert result["validation_retry_count"] == 1

    def test_가격_0원_자동_보강(self, base_state):
        """price 0원은 market_context.median_price 기반 자동 산정 → pass."""
        from app.graph.seller_copilot_nodes import validation_rules_node

        state = {**base_state}
        state["canonical_listing"] = {**base_state["canonical_listing"], "price": 0}
        state["market_context"] = {**(state.get("market_context") or {}), "median_price": 800000, "sample_count": 5}
        state["strategy"] = {**(state.get("strategy") or {}), "recommended_price": 800000}
        result = validation_rules_node(state)

        assert result["validation_passed"] is True
        assert result["canonical_listing"]["price"] > 0

    def test_보강불가_repair_action_hint_기록(self, base_state):
        """missing_model 같은 보강 불가 항목 → repair_action_hint='clarify'."""
        from app.graph.seller_copilot_nodes import validation_rules_node

        state = {**base_state}
        state["confirmed_product"] = {}  # model 누락
        result = validation_rules_node(state)

        assert result["validation_passed"] is False
        assert result["repair_action_hint"] == "clarify"

    def test_logs_누적(self, base_state):
        """validation 실행 흔적이 debug_logs에 남는지."""
        from app.graph.seller_copilot_nodes import validation_rules_node

        state = {**base_state}
        state["canonical_listing"] = {**base_state["canonical_listing"], "description": "짧음"}
        result = validation_rules_node(state)

        all_logs = " ".join(result.get("debug_logs") or [])
        assert "agent4:validation" in all_logs
        assert "auto_patch" in all_logs
