"""
에이전트 3 (판매글 생성) + 에이전트 4 (검증) 노드 테스트 (integration)
"""
from __future__ import annotations

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

pytestmark = pytest.mark.integration


# ─────────────────────────────────────────────────────────────────
# 에이전트 3: 판매글 생성 — rewrite 도구 선택
# ─────────────────────────────────────────────────────────────────

class TestCopywritingAgent:

    def test_재작성지시_있으면_rewrite_tool_호출(self, base_state):
        """rewrite_instruction이 있으면 LLM이 lc_rewrite_listing_tool을 자율 선택한다 (ReAct)"""
        import sys
        from app.graph.seller_copilot_nodes import copywriting_node

        state = {**base_state, "rewrite_instruction": "더 신뢰감 있게 작성해주세요"}
        rewritten = {**base_state["canonical_listing"], "title": "Apple iPhone 15 Pro 256GB 믿을 수 있는 판매자"}

        llm_msg = MagicMock()
        llm_msg.tool_calls = [{"name": "lc_rewrite_listing_tool", "args": {"rewrite_instruction": "더 신뢰감 있게"}}]
        llm_msg.content = ""

        tool_msg = MagicMock()
        tool_msg.tool_calls = []
        tool_msg.content = json.dumps(rewritten, ensure_ascii=False)

        mock_agent_result = {"messages": [llm_msg, tool_msg]}

        # langchain.agents.create_agent가 없는 환경에서도 ReAct 경로가 실행되도록 보장.
        # create_agent 미존재 시 except fallback에서 _run_async(mocked)가 garbage를 반환해
        # canonical_listing["title"] KeyError가 발생하는 것을 방지.
        mock_agents = MagicMock()
        mock_agents.create_agent = MagicMock(return_value=MagicMock())

        with patch("app.graph.nodes.copywriting_agent._build_react_llm", return_value=MagicMock()):
            with patch("app.graph.nodes.copywriting_agent._run_async", return_value=mock_agent_result):
                with patch.dict(sys.modules, {"langchain.agents": mock_agents}):
                    result = copywriting_node(state)

        assert result["canonical_listing"]["title"] == rewritten["title"]
        assert result["rewrite_instruction"] is None

    def test_재작성지시_없으면_신규생성(self, base_state):
        """rewrite_instruction 없으면 ListingService로 신규 생성 (LLM fallback 경로)"""
        from app.graph.seller_copilot_nodes import copywriting_node

        state = {**base_state, "canonical_listing": None, "rewrite_instruction": None}
        new_listing = {"title": "신규 생성 제목", "description": "신규 설명", "price": 950000, "tags": [], "images": []}

        with patch("app.services.listing_service.ListingService") as MockSvc:
            instance = MockSvc.return_value
            instance.build_canonical_listing = AsyncMock(return_value=new_listing)
            with patch("app.graph.nodes.copywriting_agent._build_react_llm", side_effect=ValueError("no LLM")):
                result = copywriting_node(state)

        assert result["status"] == "draft_generated"
        assert result["checkpoint"] == "B_draft_complete"

    def test_rewrite_react실패시_fallback으로_rewrite_결과_반영(self, base_state):
        """M77 회귀 방지: ReAct가 None 반환해도 rewrite_instruction이 있으면 fallback rewrite 실행"""
        from app.graph.seller_copilot_nodes import copywriting_node

        existing_listing = {**base_state["canonical_listing"], "title": "기존 제목"}
        rewritten = {**base_state["canonical_listing"], "title": "신뢰감 있는 재작성 제목"}
        state = {**base_state, "canonical_listing": existing_listing, "rewrite_instruction": "더 신뢰감 있게"}

        # ReAct 경로 실패 (None 반환) → fallback으로 rewrite
        with patch("app.graph.nodes.copywriting_agent._build_react_llm", side_effect=ValueError("no LLM")):
            with patch("app.services.listing_service.ListingService") as MockSvc:
                instance = MockSvc.return_value
                instance.rewrite_listing = AsyncMock(return_value=rewritten)
                result = copywriting_node(state)

        # 기존 제목이 아니라 rewritten 제목이어야 함
        assert result["canonical_listing"]["title"] == "신뢰감 있는 재작성 제목"
        assert result["rewrite_instruction"] is None

    def test_llm_실패시_템플릿_fallback(self, base_state):
        """LLM 호출 실패 시 템플릿 기반으로 fallback"""
        from app.graph.seller_copilot_nodes import copywriting_node

        state = {**base_state, "canonical_listing": None, "rewrite_instruction": None}

        with patch("app.graph.nodes.copywriting_agent._run_async", side_effect=Exception("LLM timeout")):
            with patch("app.services.listing_service.ListingService"):
                result = copywriting_node(state)

        assert result["canonical_listing"] is not None
        assert result["status"] == "draft_generated"

    def test_rewrite_2단_fallback_실패시_규칙기반_반영(self, base_state):
        """M84: ReAct 실패 + ListingService 실패 시에도 rewrite_instruction이 규칙 기반으로 반영된다"""
        from app.graph.seller_copilot_nodes import copywriting_node

        existing_listing = {**base_state["canonical_listing"], "title": "기존 제목", "description": "기존 설명"}
        state = {
            **base_state,
            "canonical_listing": existing_listing,
            "rewrite_instruction": "가격을 500,000원으로 낮춰주세요",
        }

        # ReAct + ListingService 모두 실패
        with patch("app.graph.nodes.copywriting_agent._build_react_llm", side_effect=ValueError("no LLM")):
            with patch("app.services.listing_service.ListingService") as MockSvc:
                MockSvc.return_value.rewrite_listing = AsyncMock(side_effect=Exception("서비스 장애"))
                result = copywriting_node(state)

        listing = result["canonical_listing"]
        # 규칙 기반으로 가격이 변경되어야 함
        assert listing["price"] == 500000
        # rewrite_instruction이 description에 반영되어야 함
        assert "500,000원" in listing["description"]
        # 소비됨
        assert result["rewrite_instruction"] is None

    def test_rewrite_fallback_중복호출_방지(self, base_state):
        """M84: _run_copywriting_agent는 None만 반환, fallback은 copywriting_node에서만 호출"""
        from app.graph.nodes.copywriting_agent import _run_copywriting_agent

        state = {**base_state, "rewrite_instruction": "수정해줘"}

        # ReAct 실패 시 None 반환 (내부에서 fallback 호출하지 않음)
        with patch("app.graph.nodes.copywriting_agent._build_react_llm", side_effect=ValueError("no LLM")):
            result = _run_copywriting_agent(
                state, state["confirmed_product"], {}, {}, [], "수정해줘"
            )

        assert result is None

    def test_rewrite_모든_fallback_실패시_기존_listing_유지(self, base_state):
        """M100: rewrite 전체 실패 시 기존 listing을 유지하고 template으로 빠지지 않음"""
        from app.graph.seller_copilot_nodes import copywriting_node

        existing = {**base_state["canonical_listing"], "title": "기존 제목", "description": "기존 설명"}
        state = {**base_state, "canonical_listing": existing, "rewrite_instruction": "더 매력적으로"}

        # ReAct + ListingService + 규칙기반 모두 실패 시나리오
        with patch("app.graph.nodes.copywriting_agent._build_react_llm", side_effect=ValueError("no LLM")):
            with patch("app.services.listing_service.ListingService") as MockSvc:
                MockSvc.return_value.rewrite_listing = AsyncMock(side_effect=Exception("장애"))
                result = copywriting_node(state)

        # 기존 listing이 유지되어야 함 (template 신규 생성 금지)
        assert result["canonical_listing"]["title"] == "기존 제목"
        # rewrite_instruction이 description에 반영
        assert "더 매력적으로" in result["canonical_listing"]["description"]
        assert result["rewrite_instruction"] is None
        # 로그에 기록
        logs = " ".join(result.get("debug_logs") or [])
        assert "rewrite_all_failed" in logs or "rule_based_rewrite" in logs

    def test_rewrite_없고_listing_없으면_template_생성(self, base_state):
        """rewrite_instruction 없고 canonical_listing도 없으면 template 정상 생성"""
        from app.graph.seller_copilot_nodes import copywriting_node

        state = {**base_state, "canonical_listing": None, "rewrite_instruction": None}

        with patch("app.graph.nodes.copywriting_agent._build_react_llm", side_effect=ValueError("no LLM")):
            with patch("app.services.listing_service.ListingService") as MockSvc:
                MockSvc.return_value.build_canonical_listing = AsyncMock(side_effect=Exception("장애"))
                result = copywriting_node(state)

        assert result["canonical_listing"] is not None
        assert result["status"] == "draft_generated"

    def test_apply_rewrite_instruction_rule_based(self, base_state):
        """M84: 규칙 기반 재작성 함수 단위 테스트"""
        from app.graph.nodes.copywriting_agent import _apply_rewrite_instruction_rule_based

        existing = {**base_state["canonical_listing"], "description": "좋은 상품입니다"}
        product = base_state["confirmed_product"]
        strategy = base_state["strategy"]

        result = _apply_rewrite_instruction_rule_based(
            existing, "가격을 300,000원으로 인하해주세요", product, strategy,
        )
        assert result["price"] == 300000
        assert "300,000원" in result["description"]


# ─────────────────────────────────────────────────────────────────
# 에이전트 4: 검증 — retry 루프
# ─────────────────────────────────────────────────────────────────

class TestValidationAgent:

    def test_정상_listing_통과(self, base_state):
        from app.graph.seller_copilot_nodes import validation_node

        result = validation_node(base_state)
        assert result["validation_passed"] is True
        assert result["checkpoint"] == "B_complete"

    def test_짧은제목_실패(self, base_state):
        from app.graph.seller_copilot_nodes import validation_node

        state = {**base_state}
        state["canonical_listing"] = {**base_state["canonical_listing"], "title": "짧"}
        result = validation_node(state)

        assert result["validation_passed"] is False
        assert result["validation_retry_count"] == 1
        error_codes = [i["code"] for i in result["validation_result"]["issues"]]
        assert "title_too_short" in error_codes

    def test_refinement_후_재검증(self, base_state):
        """refinement_node가 수정한 내용이 재검증에서 통과하는지"""
        from app.graph.seller_copilot_nodes import refinement_node, validation_node

        state = {**base_state}
        state["canonical_listing"] = {
            **base_state["canonical_listing"],
            "description": "짧음",
            "price": 0,
        }

        refined = refinement_node(state)
        assert len(refined["canonical_listing"]["description"]) >= 20
        assert refined["canonical_listing"]["price"] > 0

        validated = validation_node(refined)
        assert validated["validation_passed"] is True

    def test_tool_calls_누적(self, base_state):
        """각 에이전트가 도구를 호출하면 debug_logs에 실행 흔적이 쌓인다"""
        from app.graph.seller_copilot_nodes import validation_node, refinement_node

        state = {**base_state}
        state["canonical_listing"] = {
            **base_state["canonical_listing"],
            "description": "짧음",
            "price": 0,
        }

        after_validation = validation_node(state)
        after_refinement = refinement_node(after_validation)
        after_revalidation = validation_node(after_refinement)

        all_logs = " ".join(after_revalidation.get("debug_logs") or [])
        assert "agent4:validation" in all_logs
        assert "agent4:refinement" in all_logs
