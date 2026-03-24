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

        with patch("app.graph.nodes.copywriting_agent._build_react_llm", return_value=MagicMock()):
            with patch("app.graph.nodes.copywriting_agent._run_async", return_value=mock_agent_result):
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

    def test_llm_실패시_템플릿_fallback(self, base_state):
        """LLM 호출 실패 시 템플릿 기반으로 fallback"""
        from app.graph.seller_copilot_nodes import copywriting_node

        state = {**base_state, "canonical_listing": None, "rewrite_instruction": None}

        with patch("app.graph.nodes.copywriting_agent._run_async", side_effect=Exception("LLM timeout")):
            with patch("app.services.listing_service.ListingService"):
                result = copywriting_node(state)

        assert result["canonical_listing"] is not None
        assert result["status"] == "draft_generated"


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
