"""
LangGraph 그래프 정의 — 에이전틱 버전.

조건 분기:
1. product_identity → needs_user_input → clarification(END) or market_intelligence
2. validation → passed → package_builder or refinement (최대 2회 재시도)
3. recovery → auto_recoverable → publish_retry or publishing_failed(END)
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
        # 재시도 초과 → 그냥 통과 (사용자에게 경고만)
        return "package_builder_node"

    return "refinement_node"


def route_after_recovery(
    state: SellerCopilotState,
) -> Literal["END"]:
    """
    현재는 recovery 후 항상 END (publishing_failed 상태).
    향후 자동 재게시가 필요하면 publish_node를 추가하고 여기서 분기.
    """
    return END


def route_post_sale(
    state: SellerCopilotState,
) -> Literal["post_sale_optimization_node", "END"]:
    """sale_status가 세팅된 경우에만 최적화 에이전트 진입"""
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
    graph.add_node("recovery_node", recovery_node)                         # Agent 4: 복구
    graph.add_node("post_sale_optimization_node", post_sale_optimization_node)  # Agent 5

    # ── 메인 플로우 ──────────────────────────────────────────────
    graph.add_edge(START, "product_identity_node")

    # 분기 1: 상품 식별 결과
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

    # 분기 2: validation 결과 (재시도 포함)
    graph.add_conditional_edges(
        "validation_node",
        route_after_validation,
        {
            "refinement_node": "refinement_node",
            "package_builder_node": "package_builder_node",
        },
    )

    graph.add_edge("refinement_node", "validation_node")   # 루프: refinement → re-validate
    graph.add_edge("package_builder_node", END)
    graph.add_edge("recovery_node", END)
    graph.add_edge("post_sale_optimization_node", END)

    return graph.compile()


seller_copilot_graph = build_seller_copilot_graph()
