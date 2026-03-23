"""
LangGraph 그래프 정의 — 에이전틱 버전.

노드 흐름:
START → product_identity → market_intelligence → pricing → copywriting
     → validation → (refinement 루프) → package_builder → publish_node
     → recovery_node (실패 시) → END

recovery_node는 publish 실패 시에만 진입.
"""
from __future__ import annotations

from typing import Literal

from langgraph.graph import END, START, StateGraph

from app.graph.seller_copilot_nodes import (
    clarification_node,
    copywriting_node,
    market_intelligence_node,
    package_builder_node,
    post_sale_optimization_node,
    pricing_strategy_node,
    product_identity_node,
    publish_node,
    recovery_node,
    refinement_node,
    validation_node,
)
from app.graph.seller_copilot_state import SellerCopilotState

MAX_VALIDATION_RETRIES = 2
MAX_PUBLISH_RETRIES = 2


# ── 라우터 함수들 ──────────────────────────────────────────────────

def route_after_product_identity(
    state: SellerCopilotState,
) -> Literal["clarification_node", "market_intelligence_node"]:
    if state.get("needs_user_input", False):
        return "clarification_node"
    return "market_intelligence_node"


def route_after_validation(
    state: SellerCopilotState,
) -> Literal["refinement_node", "package_builder_node"]:
    if state.get("validation_passed", False):
        return "package_builder_node"
    retry = int(state.get("validation_retry_count") or 0)
    if retry >= MAX_VALIDATION_RETRIES:
        return "package_builder_node"
    return "refinement_node"


def route_after_publish(
    state: SellerCopilotState,
) -> Literal["recovery_node", "__end__"]:
    """게시 결과에 따라 복구 에이전트 진입 여부 결정"""
    publish_results = state.get("publish_results") or {}
    if not publish_results:
        return END
    any_failed = any(not r.get("success") for r in publish_results.values())
    if any_failed:
        return "recovery_node"
    return END


def route_after_recovery(
    state: SellerCopilotState,
) -> Literal["publish_node", "__end__"]:
    """auto_recoverable이면 publish 재시도, 아니면 종료"""
    should_retry = state.get("should_retry_publish", False)
    retry_count = int(state.get("publish_retry_count") or 0)
    if should_retry and retry_count <= MAX_PUBLISH_RETRIES:
        return "publish_node"
    return END


def route_post_sale(
    state: SellerCopilotState,
) -> Literal["post_sale_optimization_node", "__end__"]:
    sale_status = state.get("sale_status")
    if sale_status in ("sold", "unsold"):
        return "post_sale_optimization_node"
    return END


# ── 그래프 빌더 ────────────────────────────────────────────────────

def build_seller_copilot_graph():
    graph = StateGraph(SellerCopilotState)

    # 노드 등록
    graph.add_node("product_identity_node", product_identity_node)
    graph.add_node("clarification_node", clarification_node)
    graph.add_node("market_intelligence_node", market_intelligence_node)
    graph.add_node("pricing_strategy_node", pricing_strategy_node)
    graph.add_node("copywriting_node", copywriting_node)
    graph.add_node("validation_node", validation_node)
    graph.add_node("refinement_node", refinement_node)
    graph.add_node("package_builder_node", package_builder_node)
    graph.add_node("publish_node", publish_node)          # 게시 실행
    graph.add_node("recovery_node", recovery_node)         # 게시 실패 복구 (Agent 4)
    graph.add_node("post_sale_optimization_node", post_sale_optimization_node)  # Agent 5

    # ── 메인 플로우 ──────────────────────────────────────────────
    graph.add_edge(START, "product_identity_node")

    graph.add_conditional_edges(
        "product_identity_node",
        route_after_product_identity,
        {
            "clarification_node": "clarification_node",
            "market_intelligence_node": "market_intelligence_node",
        },
    )

    graph.add_edge("clarification_node", END)
    graph.add_edge("market_intelligence_node", "pricing_strategy_node")
    graph.add_edge("pricing_strategy_node", "copywriting_node")
    graph.add_edge("copywriting_node", "validation_node")

    graph.add_conditional_edges(
        "validation_node",
        route_after_validation,
        {
            "refinement_node": "refinement_node",
            "package_builder_node": "package_builder_node",
        },
    )

    graph.add_edge("refinement_node", "validation_node")
    graph.add_edge("package_builder_node", "publish_node")   # ← 패키지 완성 후 바로 게시

    # ── 게시 → 복구 분기 ─────────────────────────────────────────
    graph.add_conditional_edges(
        "publish_node",
        route_after_publish,
        {
            "recovery_node": "recovery_node",
            END: END,
        },
    )

    # ── 복구 → 재시도 or 종료 ────────────────────────────────────
    graph.add_conditional_edges(
        "recovery_node",
        route_after_recovery,
        {
            "publish_node": "publish_node",
            END: END,
        },
    )

    graph.add_edge("post_sale_optimization_node", END)

    return graph.compile()


seller_copilot_graph = build_seller_copilot_graph()
