"""
에이전트 1 (상품 식별) + 에이전트 2 (시세 분석) 노드 테스트 (integration)
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch

pytestmark = pytest.mark.integration


# ─────────────────────────────────────────────────────────────────
# 에이전트 1: 상품 식별 — 분기 테스트
# ─────────────────────────────────────────────────────────────────

class TestProductIdentityAgent:

    def test_user_input_확정(self):
        """사용자 입력이 있으면 도구 없이 바로 confirmed_product 설정"""
        from app.graph.seller_copilot_nodes import product_identity_node

        state = {
            "user_product_input": {"brand": "Samsung", "model": "Galaxy S24", "category": "smartphone"},
            "product_candidates": [],
            "tool_calls": [], "debug_logs": [], "error_history": [],
        }
        result = product_identity_node(state)

        assert result["confirmed_product"]["model"] == "Galaxy S24"
        assert result["confirmed_product"]["source"] == "user_input"
        assert result["needs_user_input"] is False
        assert result["checkpoint"] == "A_complete"

    def test_high_confidence_vision_확정(self):
        """Vision confidence >= 0.6이면 자동 확정"""
        from app.graph.seller_copilot_nodes import product_identity_node

        state = {
            "user_product_input": {},
            "product_candidates": [
                {"brand": "Apple", "model": "iPhone 15", "category": "smartphone", "confidence": 0.91}
            ],
            "tool_calls": [], "debug_logs": [], "error_history": [],
        }
        result = product_identity_node(state)

        assert result["confirmed_product"]["model"] == "iPhone 15"
        assert result["needs_user_input"] is False

    def test_low_confidence_사용자입력요청(self):
        """confidence < 0.6이면 사용자 입력 요청으로 분기"""
        from app.graph.seller_copilot_nodes import product_identity_node

        state = {
            "user_product_input": {},
            "product_candidates": [
                {"brand": "Unknown", "model": "Unknown", "category": "unknown", "confidence": 0.3}
            ],
            "tool_calls": [], "debug_logs": [], "error_history": [],
        }
        result = product_identity_node(state)

        assert result["needs_user_input"] is True
        assert result["clarification_prompt"] is not None
        assert result["checkpoint"] == "A_needs_user_input"

    def test_empty_candidates_사용자입력요청(self):
        """candidates 없으면 사용자 입력 요청"""
        from app.graph.seller_copilot_nodes import product_identity_node

        state = {
            "user_product_input": {},
            "product_candidates": [],
            "tool_calls": [], "debug_logs": [], "error_history": [],
        }
        result = product_identity_node(state)
        assert result["needs_user_input"] is True


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
