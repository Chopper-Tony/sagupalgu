"""
Agent 5 — 판매 후 최적화 에이전트

노드:
  post_sale_optimization_node  — sale_status 기반 가격 인하 제안
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.graph.seller_copilot_state import SellerCopilotState
from app.graph.nodes.helpers import _log, _record_tool_call, _run_async


def post_sale_optimization_node(state: SellerCopilotState) -> SellerCopilotState:
    _log(state, "agent5:post_sale_optimization:start")

    sale_status = state.get("sale_status")
    canonical = state.get("canonical_listing") or {}
    product = state.get("confirmed_product") or {}

    if sale_status == "sold":
        _log(state, "agent5:sold → no action needed")
        state["status"] = "completed"
        return state

    if sale_status != "unsold":
        _log(state, f"agent5:sale_status={sale_status} → awaiting input")
        state["status"] = "awaiting_sale_status_update"
        return state

    # ── 도구 선택: 가격 최적화 ────────────────────────────────────
    _log(state, "agent5:selecting_tool:price_optimization_tool")
    from app.tools.agentic_tools import price_optimization_tool

    days_listed = 7
    followup_str = state.get("followup_due_at")
    if followup_str:
        try:
            followup_dt = datetime.fromisoformat(followup_str)
            days_listed = max(1, (datetime.now(timezone.utc) - followup_dt).days + 7)
        except Exception:
            pass

    opt_call = _run_async(lambda: price_optimization_tool(
        canonical_listing=canonical,
        confirmed_product=product,
        sale_status=sale_status,
        days_listed=days_listed,
    ))
    _record_tool_call(state, opt_call)

    opt_output = opt_call.get("output") or {}
    if opt_output.get("type"):
        state["optimization_suggestion"] = opt_output
        state["status"] = "optimization_suggested"
        _log(state, f"agent5:suggestion type={opt_output.get('type')} price={opt_output.get('suggested_price')}")
    else:
        state["status"] = "awaiting_sale_status_update"
        _log(state, "agent5:no_suggestion_generated")

    return state
