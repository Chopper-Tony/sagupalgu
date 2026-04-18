"""
에이전트 1 (상품 식별) + 에이전트 2 (시세 분석) 노드 테스트 (integration)
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

pytestmark = pytest.mark.integration


# ─────────────────────────────────────────────────────────────────
# 에이전트 1: 상품 식별 — 분기 테스트
# ─────────────────────────────────────────────────────────────────

class TestProductIdentityAgent:

    def test_user_input_확정(self):
        """사용자 입력이 있으면 도구 없이 바로 confirmed_product 설정"""
        from app.graph.seller_copilot_nodes import product_gate_node

        state = {
            "user_product_input": {"brand": "Samsung", "model": "Galaxy S24", "category": "smartphone"},
            "product_candidates": [],
            "tool_calls": [], "debug_logs": [], "error_history": [],
        }
        result = product_gate_node(state)

        assert result["confirmed_product"]["model"] == "Galaxy S24"
        assert result["confirmed_product"]["source"] == "user_input"
        assert result["needs_user_input"] is False
        assert result["checkpoint"] == "A_complete"

    def test_high_confidence_vision_확정(self):
        """Vision confidence >= 0.6이면 자동 확정"""
        from app.graph.seller_copilot_nodes import product_gate_node

        state = {
            "user_product_input": {},
            "product_candidates": [
                {"brand": "Apple", "model": "iPhone 15", "category": "smartphone", "confidence": 0.91}
            ],
            "tool_calls": [], "debug_logs": [], "error_history": [],
        }
        result = product_gate_node(state)

        assert result["confirmed_product"]["model"] == "iPhone 15"
        assert result["needs_user_input"] is False

    def test_low_confidence_사용자입력요청(self):
        """confidence < 0.6이면 사용자 입력 요청으로 분기"""
        from app.graph.seller_copilot_nodes import product_gate_node

        state = {
            "user_product_input": {},
            "product_candidates": [
                {"brand": "Unknown", "model": "Unknown", "category": "unknown", "confidence": 0.3}
            ],
            "tool_calls": [], "debug_logs": [], "error_history": [],
        }
        result = product_gate_node(state)

        assert result["needs_user_input"] is True
        assert result["clarification_prompt"] is not None
        assert result["checkpoint"] == "A_needs_user_input"

    def test_empty_candidates_사용자입력요청(self):
        """candidates 없으면 사용자 입력 요청"""
        from app.graph.seller_copilot_nodes import product_gate_node

        state = {
            "user_product_input": {},
            "product_candidates": [],
            "tool_calls": [], "debug_logs": [], "error_history": [],
        }
        result = product_gate_node(state)
        assert result["needs_user_input"] is True


# ─────────────────────────────────────────────────────────────────
# PR4-2 신규: ReAct 활성화 시나리오 (LLM mock)
# ─────────────────────────────────────────────────────────────────

class TestProductIdentityAgentReAct:
    """enable_product_identity_agent=True + LLM mock으로 ReAct 분기 검증."""

    def _enable_flag(self):
        """settings를 mock해 flag=True로 강제."""
        mock_settings = MagicMock()
        mock_settings.enable_product_identity_agent = True
        return patch("app.core.config.get_settings", return_value=mock_settings)

    def test_flag_off_바로_deterministic_fallback(self):
        """flag off (default)면 ReAct 안 거치고 deterministic 동작."""
        from app.graph.nodes.product_agent import product_identity_agent

        state = {
            "user_product_input": {},
            "product_candidates": [
                {"brand": "Apple", "model": "iPhone 15", "category": "smartphone", "confidence": 0.85}
            ],
            "tool_calls": [], "debug_logs": [], "error_history": [],
        }
        result = product_identity_agent(state)
        # _build_react_llm 호출 안 됨 → deterministic 경로 → vision_confirmed
        assert result["confirmed_product"]["model"] == "iPhone 15"
        assert result["confirmed_product"]["source"] == "vision"

    def test_flag_on_user_input_있으면_ReAct_skip(self):
        """flag on이라도 user_input이 가장 강한 신호 → ReAct 안 거치고 즉시 확정."""
        from app.graph.nodes.product_agent import product_identity_agent

        state = {
            "user_product_input": {"brand": "Samsung", "model": "Galaxy S24", "category": "smartphone"},
            "product_candidates": [],
            "tool_calls": [], "debug_logs": [], "error_history": [],
        }
        with self._enable_flag():
            result = product_identity_agent(state)

        assert result["confirmed_product"]["model"] == "Galaxy S24"
        assert result["confirmed_product"]["source"] == "user_input"

    def test_flag_on_LLM_None이면_deterministic_fallback(self):
        """flag on + _build_react_llm None → deterministic으로 강등."""
        from app.graph.nodes.product_agent import product_identity_agent

        state = {
            "user_product_input": {},
            "product_candidates": [
                {"brand": "Apple", "model": "iPhone 15", "category": "smartphone", "confidence": 0.85}
            ],
            "tool_calls": [], "debug_logs": [], "error_history": [],
        }
        with self._enable_flag():
            with patch("app.graph.nodes.helpers._build_react_llm", return_value=None):
                result = product_identity_agent(state)

        # deterministic 경로의 vision_confirmed 결과
        assert result["confirmed_product"]["model"] == "iPhone 15"
        assert result["confirmed_product"]["source"] == "vision"

    def test_flag_on_ReAct_예외시_deterministic_fallback(self):
        """flag on + ReAct 호출 자체 예외 → deterministic 강등 + failure_mode 기록."""
        from app.graph.nodes.product_agent import product_identity_agent

        state = {
            "user_product_input": {},
            "product_candidates": [
                {"brand": "Apple", "model": "iPhone 15", "category": "smartphone", "confidence": 0.85}
            ],
            "tool_calls": [], "debug_logs": [], "error_history": [],
        }
        with self._enable_flag():
            with patch("app.graph.nodes.product_agent._run_react", side_effect=Exception("LLM down")):
                result = product_identity_agent(state)

        assert result.get("product_identity_failure_mode") == "react_exception"
        # deterministic 결과 확인
        assert result["confirmed_product"]["model"] == "iPhone 15"

    def test_flag_on_ReAct_정상_confirmed_반환(self):
        """flag on + ReAct가 confirmed JSON 반환 → state에 그대로 적용."""
        from app.graph.nodes.product_agent import product_identity_agent

        state = {
            "user_product_input": {},
            "product_candidates": [
                {"brand": "Apple", "model": "iPhone 15", "category": "smartphone", "confidence": 0.55}
            ],
            "image_paths": ["img1.jpg"],
            "tool_calls": [], "debug_logs": [], "error_history": [],
        }
        # _run_react가 catalog match 통한 confirmed 반환했다고 가정
        react_result = {
            "confirmed_product": {
                "brand": "Apple", "model": "iPhone 15 Pro", "category": "smartphone",
                "confidence": 0.82, "source": "catalog",
            },
            "needs_user_input": False,
            "rationale": "catalog top_match=0.82",
        }
        with self._enable_flag():
            with patch("app.graph.nodes.product_agent._run_react", return_value=react_result):
                result = product_identity_agent(state)

        assert result["confirmed_product"]["model"] == "iPhone 15 Pro"  # ReAct가 보정
        assert result["confirmed_product"]["source"] == "catalog"
        assert result["needs_user_input"] is False
        assert result["checkpoint"] == "A_complete"

    def test_flag_on_ReAct_clarify_요청(self):
        """flag on + ReAct가 needs_user_input=True 반환 → clarification 분기."""
        from app.graph.nodes.product_agent import product_identity_agent

        state = {
            "user_product_input": {},
            "product_candidates": [
                {"brand": "?", "model": "?", "category": "etc", "confidence": 0.3}
            ],
            "image_paths": ["img1.jpg"],
            "tool_calls": [], "debug_logs": [], "error_history": [],
        }
        react_result = {
            "needs_user_input": True,
            "clarification_prompt": "정확한 모델명을 알려주세요.",
            "clarification_questions": [
                {"id": "model_name", "question": "정확한 모델명?"},
            ],
            "rationale": "reanalyze x2, catalog cold_start → clarify",
        }
        with self._enable_flag():
            with patch("app.graph.nodes.product_agent._run_react", return_value=react_result):
                result = product_identity_agent(state)

        assert result["needs_user_input"] is True
        assert "모델명" in result["clarification_prompt"]
        assert result["pre_listing_questions"] == react_result["clarification_questions"]
        assert result["checkpoint"] == "A_needs_user_input"

    def test_flag_on_ReAct_contract_violation시_fallback(self):
        """ReAct가 needs_user_input=False인데 model 누락 → contract_violation + fallback."""
        from app.graph.nodes.product_agent import product_identity_agent

        state = {
            "user_product_input": {},
            "product_candidates": [
                {"brand": "Apple", "model": "iPhone 15", "category": "smartphone", "confidence": 0.85}
            ],
            "tool_calls": [], "debug_logs": [], "error_history": [],
        }
        bad_result = {
            "confirmed_product": {"brand": "Apple", "model": "", "category": "smartphone"},
            "needs_user_input": False,
        }
        with self._enable_flag():
            with patch("app.graph.nodes.product_agent._run_react", return_value=bad_result):
                result = product_identity_agent(state)

        assert result.get("product_identity_failure_mode") == "product_identity_contract_violation"
        # deterministic fallback로 vision_confirmed
        assert result["confirmed_product"]["model"] == "iPhone 15"


# ─────────────────────────────────────────────────────────────────
# 에이전트 2: 시세 분석 — 도구 선택 자율성
# ─────────────────────────────────────────────────────────────────

class TestMarketIntelligenceAgent:

    @pytest.mark.asyncio
    async def test_충분한표본_rag_스킵(self, confirmed_product):
        """sample_count >= 3이면 RAG 도구를 호출하지 않는다"""
        from app.graph.seller_copilot_nodes import market_intelligence_node

        crawl_output = {
            "median_price": 980000, "price_band": [900000, 1100000],
            "sample_count": 12, "crawler_sources": ["번개장터"],
        }

        with patch("app.tools.agentic_tools.market_crawl_tool",
                   new_callable=AsyncMock) as mock_crawl, \
             patch("app.tools.agentic_tools.rag_price_tool",
                   new_callable=AsyncMock) as mock_rag:

            mock_crawl.return_value = {
                "tool_name": "market_crawl_tool", "output": crawl_output, "success": True
            }

            state = {
                "confirmed_product": confirmed_product,
                "market_context": None,
                "tool_calls": [], "debug_logs": [], "error_history": [],
            }

            with patch("app.graph.nodes.market_agent._run_async", side_effect=lambda c: mock_crawl.return_value):
                result = market_intelligence_node(state)

            mock_rag.assert_not_called()
            assert result["market_context"]["sample_count"] == 12

    def test_기존_market_context_스킵(self, confirmed_product, market_context):
        """이미 market_context가 있으면 도구 호출 없이 스킵"""
        from app.graph.seller_copilot_nodes import market_intelligence_node

        state = {
            "confirmed_product": confirmed_product,
            "market_context": market_context,
            "tool_calls": [], "debug_logs": [], "error_history": [],
        }

        with patch("app.tools.agentic_tools.market_crawl_tool") as mock_crawl:
            result = market_intelligence_node(state)
            mock_crawl.assert_not_called()

        assert result["checkpoint"] == "B_market_complete"

    def test_확정상품없으면_실패(self):
        """confirmed_product 없으면 status=failed"""
        from app.graph.seller_copilot_nodes import market_intelligence_node

        state = {
            "confirmed_product": None,
            "market_context": None,
            "tool_calls": [], "debug_logs": [], "error_history": [],
        }
        result = market_intelligence_node(state)
        assert result["status"] == "failed"
        assert result["last_error"] is not None

    def test_market_intelligence_tool_calls_기록(self, confirmed_product):
        """market_intelligence_node가 도구 호출 결과를 tool_calls에 기록한다"""
        from app.graph.seller_copilot_nodes import market_intelligence_node

        crawl_output = {
            "median_price": 980000, "price_band": [900000, 1100000],
            "sample_count": 10, "crawler_sources": ["번개장터"],
        }
        mock_result = {"tool_name": "market_crawl_tool", "output": crawl_output, "success": True}

        state = {
            "confirmed_product": confirmed_product,
            "market_context": None,
            "tool_calls": [], "debug_logs": [], "error_history": [],
        }

        with patch("app.graph.nodes.market_agent._run_async", return_value=mock_result):
            result = market_intelligence_node(state)

        assert len(result["tool_calls"]) >= 1
        assert result["tool_calls"][0]["tool_name"] == "market_crawl_tool"
        assert result["tool_calls"][0]["success"] is True
