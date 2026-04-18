"""
Agent 5 — 판매 후 최적화

분류 (Target Architecture, 4+2+5):
  post_sale_optimization_node → Deterministic Node (PR1 알리아스: post_sale_policy_node)
                                price_optimization_tool 결정론적 호출. LLM 호출 없음.
                                (도구를 호출하지만 selection 없음 — sale_status 분기뿐).
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
        except (ValueError, TypeError):
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


# ── PR1 알리아스 (Target Architecture: 4+2+5 재분류) ──────────────────
# 동작 변화 0. PR2/3에서 신 이름이 service layer·graph builder에서 사용되기 시작.
# TODO(PR3-cleanup): graph builder·service가 신 이름으로 완전 전환되면 이 알리아스 제거.
post_sale_policy_node = post_sale_optimization_node
