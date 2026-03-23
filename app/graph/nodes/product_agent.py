"""
Agent 1 — 상품 식별 에이전트

노드:
  product_identity_node  — Vision 결과 또는 사용자 입력으로 상품 확정
  clarification_node     — 사용자 입력 대기 (graph END 후 재진입 시)
"""
from __future__ import annotations

from app.graph.seller_copilot_state import ConfirmedProduct, SellerCopilotState
from app.graph.nodes.helpers import _log


def product_identity_node(state: SellerCopilotState) -> SellerCopilotState:
    _log(state, "agent1:product_identity:start")

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
        _log(state, "agent1:product_identity:user_input_confirmed")
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
            _log(state, f"agent1:product_identity:low_confidence={confidence:.2f}")
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
        _log(state, f"agent1:product_identity:vision_confirmed confidence={confidence:.2f}")
        return state

    # 경로 C: candidates도 없음 → 사용자 입력 요청
    state["needs_user_input"] = True
    state["clarification_prompt"] = (
        "상품 정보를 파악하지 못했습니다. "
        "모델명을 직접 입력해주시거나 사진을 다시 업로드해주세요."
    )
    state["checkpoint"] = "A_needs_user_input"
    state["status"] = "awaiting_product_confirmation"
    _log(state, "agent1:product_identity:no_candidates")
    return state


def clarification_node(state: SellerCopilotState) -> SellerCopilotState:
    """사용자 입력 대기 — 이 노드에서 graph는 END로 중단되고 사용자 응답을 기다린다"""
    _log(state, "agent1:clarification:waiting_for_user_input")
    state["checkpoint"] = "A_needs_user_input"
    state["status"] = "awaiting_product_confirmation"
    return state
