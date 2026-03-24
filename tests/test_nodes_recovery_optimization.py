"""
에이전트 4 (복구) + 에이전트 5 (최적화) + 패키지 빌더 노드 테스트 (integration)
"""
from __future__ import annotations

import pytest
from unittest.mock import patch

pytestmark = pytest.mark.integration


# ─────────────────────────────────────────────────────────────────
# 에이전트 4: 복구 — 진단 + Discord 알림
# ─────────────────────────────────────────────────────────────────

class TestRecoveryAgent:

    def test_네트워크오류_자동복구가능(self):
        from app.tools.agentic_tools import diagnose_publish_failure_tool

        result = diagnose_publish_failure_tool(
            platform="bunjang",
            error_code="publish_exception",
            error_message="Connection timeout occurred",
        )
        diag = result["output"]
        assert diag["likely_cause"] == "network"
        assert diag["auto_recoverable"] is True

    def test_로그인만료_자동복구불가(self):
        from app.tools.agentic_tools import diagnose_publish_failure_tool

        result = diagnose_publish_failure_tool(
            platform="joongna",
            error_code="auth_error",
            error_message="Session expired, please login again",
        )
        diag = result["output"]
        assert diag["likely_cause"] == "login_expired"
        assert diag["auto_recoverable"] is False

    def test_콘텐츠정책위반_자동복구불가(self):
        from app.tools.agentic_tools import diagnose_publish_failure_tool

        result = diagnose_publish_failure_tool(
            platform="bunjang",
            error_code="content_rejected",
            error_message="Content policy violation detected",
        )
        diag = result["output"]
        assert diag["likely_cause"] == "content_policy"
        assert diag["auto_recoverable"] is False

    def test_recovery_node_실패시_tool_기록(self, base_state):
        """recovery_node 실행 시 tool_calls에 진단 기록이 쌓인다"""
        from app.graph.seller_copilot_nodes import recovery_node

        state = {
            **base_state,
            "publish_results": {
                "bunjang": {
                    "success": False,
                    "error_code": "publish_exception",
                    "error_message": "Connection timeout",
                }
            },
        }

        with patch("app.graph.nodes.recovery_agent._build_react_llm", return_value=None):
            with patch("app.graph.nodes.recovery_agent._run_async", return_value={
                "tool_name": "discord_alert_tool", "output": {"sent": False}, "success": True
            }):
                result = recovery_node(state)

        assert len(result["tool_calls"]) >= 1
        tool_names = [c["tool_name"] for c in result["tool_calls"]]
        assert "diagnose_publish_failure_tool" in tool_names

    def test_recovery_재시도횟수_초과(self, base_state):
        """publish_retry_count >= 2면 publishing_failed로 전환"""
        from app.graph.seller_copilot_nodes import recovery_node

        state = {
            **base_state,
            "publish_retry_count": 2,
            "publish_results": {
                "bunjang": {"success": False, "error_code": "unknown", "error_message": "unknown error"}
            },
        }

        with patch("app.graph.nodes.recovery_agent._build_react_llm", return_value=None):
            with patch("app.graph.nodes.recovery_agent._run_async", return_value={
                "tool_name": "discord_alert_tool", "output": {"sent": False}, "success": True
            }):
                result = recovery_node(state)

        assert result["status"] == "publishing_failed"
        assert result["checkpoint"] == "D_publish_failed"


# ─────────────────────────────────────────────────────────────────
# 에이전트 5: 판매 후 최적화
# ─────────────────────────────────────────────────────────────────

class TestPostSaleOptimizationAgent:

    @pytest.mark.asyncio
    async def test_미판매_가격인하_제안(self, confirmed_product, canonical_listing):
        from app.tools.agentic_tools import price_optimization_tool

        result = await price_optimization_tool(
            canonical_listing=canonical_listing,
            confirmed_product=confirmed_product,
            sale_status="unsold",
            days_listed=7,
        )
        output = result["output"]
        assert output["type"] == "price_drop"
        assert output["suggested_price"] < canonical_listing["price"]
        assert output["urgency"] == "medium"

    @pytest.mark.asyncio
    async def test_장기미판매_높은긴급도(self, confirmed_product, canonical_listing):
        from app.tools.agentic_tools import price_optimization_tool

        result = await price_optimization_tool(
            canonical_listing=canonical_listing,
            confirmed_product=confirmed_product,
            sale_status="unsold",
            days_listed=15,
        )
        output = result["output"]
        assert output["urgency"] == "high"
        assert output["suggested_price"] <= int(canonical_listing["price"] * 0.91)

    @pytest.mark.asyncio
    async def test_판매완료_제안없음(self, confirmed_product, canonical_listing):
        from app.tools.agentic_tools import price_optimization_tool

        result = await price_optimization_tool(
            canonical_listing=canonical_listing,
            confirmed_product=confirmed_product,
            sale_status="sold",
            days_listed=3,
        )
        assert result["output"].get("suggestion") is None or result["output"].get("type") is None

    def test_판매완료_노드_상태전환(self, base_state):
        from app.graph.seller_copilot_nodes import post_sale_optimization_node

        state = {**base_state, "sale_status": "sold"}
        result = post_sale_optimization_node(state)
        assert result["status"] == "completed"

    def test_미판매_최적화노드_실행(self, base_state, canonical_listing):
        from app.graph.seller_copilot_nodes import post_sale_optimization_node

        state = {**base_state, "sale_status": "unsold", "canonical_listing": canonical_listing}
        opt_output = {
            "type": "price_drop", "current_price": 950600,
            "suggested_price": 903000, "reason": "7일 미판매", "urgency": "medium"
        }
        mock_result = {"tool_name": "price_optimization_tool", "output": opt_output, "success": True}

        with patch("app.graph.nodes.optimization_agent._run_async", return_value=mock_result):
            result = post_sale_optimization_node(state)

        assert result["optimization_suggestion"]["type"] == "price_drop"
        assert result["status"] == "optimization_suggested"
        assert any(c["tool_name"] == "price_optimization_tool" for c in result["tool_calls"])


# ─────────────────────────────────────────────────────────────────
# 패키지 빌더
# ─────────────────────────────────────────────────────────────────

class TestPackageBuilder:

    def test_플랫폼별_가격_차등(self, base_state):
        from app.graph.seller_copilot_nodes import package_builder_node

        state = {**base_state, "selected_platforms": ["bunjang", "joongna", "daangn"]}
        result = package_builder_node(state)

        base_price = base_state["canonical_listing"]["price"]
        assert result["platform_packages"]["bunjang"]["price"] == base_price + 10000
        assert result["platform_packages"]["joongna"]["price"] == base_price
        assert result["platform_packages"]["daangn"]["price"] == max(base_price - 4000, 0)

    def test_패키지_필수필드(self, base_state):
        from app.graph.seller_copilot_nodes import package_builder_node

        result = package_builder_node(base_state)
        for platform, pkg in result["platform_packages"].items():
            assert "title" in pkg
            assert "body" in pkg
            assert "price" in pkg
            assert "images" in pkg
