"""
Agent 1 — 상품 식별 (Tool Agent로 승격 예정, 별도 트랙)

분류 (Target Architecture, 4+2+5):
  product_gate_node  → Deterministic Node
                       Vision 결과·사용자 입력으로 상품 확정. LLM 호출 없음.
                       Product Identity 승격 (lc_image_reanalyze_tool 도입 + ReAct 전환)은
                       별도 PR 트랙 (entry criteria 충족 후 진행).
"""
from __future__ import annotations

from app.graph.seller_copilot_state import ConfirmedProduct, SellerCopilotState
from app.graph.nodes.helpers import _log


def product_gate_node(state: SellerCopilotState) -> SellerCopilotState:
    """Vision 결과·사용자 입력으로 상품을 확정하는 deterministic gate."""
    _log(state, "agent1:product_gate:start")

    user_input = state.get("user_product_input") or {}
    candidates = state.get("product_candidates") or []

    # 경로 A: 사용자가 직접 입력한 경우 → 도구 불필요, 바로 확정
    if user_input and user_input.get("model"):
        confirmed = ConfirmedProduct(
            brand=user_input.get("brand", ""),
            model=user_input.get("model", ""),
            category=user_input.get("category", ""),
            confidence=1.0,
            source="user_input",
            storage=user_input.get("storage", ""),
        )
        state["confirmed_product"] = confirmed
        state["needs_user_input"] = False
        state["clarification_prompt"] = None
        state["checkpoint"] = "A_complete"
        state["status"] = "product_confirmed"
        _log(state, "agent1:product_gate:user_input_confirmed")
        return state

    # 경로 B: Vision 결과(candidates)가 이미 있는 경우
    if candidates:
        best = candidates[0]
        confidence = float(best.get("confidence", 0.0) or 0.0)
        model = (best.get("model") or "").strip().lower()

        # 에이전트 판단: confidence 낮으면 사용자 입력 요청
        if confidence < 0.6 or model in {"unknown", ""}:
            state["needs_user_input"] = True
            state["clarification_prompt"] = (
                "사진만으로 모델명을 정확히 식별하지 못했습니다. "
                "모델명을 직접 입력해 주세요."
            )
            state["checkpoint"] = "A_needs_user_input"
            state["status"] = "awaiting_product_confirmation"
            _log(state, f"agent1:product_gate:low_confidence={confidence:.2f}")
            return state

        # confidence 충분 → 확정
        confirmed = ConfirmedProduct(
            brand=best.get("brand", ""),
            model=best.get("model", ""),
            category=best.get("category", ""),
            confidence=confidence,
            source=best.get("source", "vision"),
            storage=best.get("storage", ""),
        )
        state["confirmed_product"] = confirmed
        state["needs_user_input"] = False
        state["clarification_prompt"] = None
        state["checkpoint"] = "A_complete"
        state["status"] = "product_confirmed"
        _log(state, f"agent1:product_gate:vision_confirmed confidence={confidence:.2f}")
        return state

    # 경로 C: candidates도 없음 → 사용자 입력 요청
    state["needs_user_input"] = True
    state["clarification_prompt"] = (
        "상품 정보를 파악하지 못했습니다. "
        "모델명을 직접 입력해주시거나 사진을 다시 업로드해주세요."
    )
    state["checkpoint"] = "A_needs_user_input"
    state["status"] = "awaiting_product_confirmation"
    _log(state, "agent1:product_gate:no_candidates")
    return state


# ─────────────────────────────────────────────────────────────────────
# PR4-cleanup REMOVED (호출 시 ImportError 발생 — 의도된 동작):
#   - product_identity_node (alias) → use product_gate_node
#   - clarification_node (deprecated wrapper) →
#       use app.graph.nodes.clarification_node.clarification_node
# 이유: 알리아스/wrapper가 영구 호환 layer로 굳지 않게 PR4-cleanup에서 완전 제거.
# 다시 alias를 추가하지 말 것 (architecture.md "노드 이름 일관성 원칙" 참조).
# ─────────────────────────────────────────────────────────────────────
