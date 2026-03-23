"""
RecoveryService — 게시 실패 복구 오케스트레이터.

SessionService가 graph internals를 직접 알지 않아도 되도록 격리.
"""
from __future__ import annotations

from typing import Any, Dict


class RecoveryService:
    def run_recovery(
        self,
        session_id: str,
        product_data: Dict[str, Any],
        publish_results: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        게시 실패 시 Agent 4 복구 노드를 실행하고 결과를 반환.

        Returns:
            {
                "publish_diagnostics": [...],
                "tool_calls": [...],
            }
        """
        from app.graph.nodes.recovery_agent import recovery_node
        from app.graph.seller_copilot_state import create_initial_state

        state = create_initial_state(
            session_id=session_id,
            image_paths=product_data.get("image_paths") or [],
        )
        state["publish_results"] = publish_results
        state["confirmed_product"] = product_data.get("confirmed_product")

        final_state = recovery_node(state)
        return {
            "publish_diagnostics": final_state.get("publish_diagnostics") or [],
            "tool_calls": final_state.get("tool_calls") or [],
        }
