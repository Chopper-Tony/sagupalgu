"""
OptimizationService — 판매 후 최적화 오케스트레이터.

SessionService가 graph internals를 직접 알지 않아도 되도록 격리.
"""
from __future__ import annotations

from typing import Any, Dict, Optional


class OptimizationService:
    def run_post_sale_optimization(
        self,
        session_id: str,
        product_data: Dict[str, Any],
        listing_data: Dict[str, Any],
        sale_status: str,
        followup_due_at: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        판매 상태 입력 시 Agent 5 최적화 노드를 실행하고 결과를 반환.

        Returns:
            {
                "optimization_suggestion": {...} | None,
                "status": str,
                "tool_calls": [...],
            }
        """
        # PR4-cleanup: 신 이름 (post_sale_policy_node) 직접 import.
        from app.graph.nodes.optimization_agent import post_sale_policy_node
        from app.graph.seller_copilot_state import create_initial_state

        state = create_initial_state(
            session_id=session_id,
            image_paths=product_data.get("image_paths") or [],
        )
        state["sale_status"] = sale_status
        state["canonical_listing"] = listing_data.get("canonical_listing")
        state["confirmed_product"] = product_data.get("confirmed_product")
        state["followup_due_at"] = followup_due_at

        final_state = post_sale_policy_node(state)
        return {
            "optimization_suggestion": final_state.get("optimization_suggestion"),
            "status": final_state.get("status"),
            "tool_calls": final_state.get("tool_calls") or [],
        }
