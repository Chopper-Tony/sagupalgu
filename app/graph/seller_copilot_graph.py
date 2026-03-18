from __future__ import annotations

from typing import Literal

from langgraph.graph import END, START, StateGraph

from app.graph.seller_copilot_nodes import (
    clarification_node,
    copywriting_node,
    market_intelligence_node,
    package_builder_node,
    pricing_strategy_node,
    product_identity_node,
    refinement_node,
    validation_node,
)
from app.graph.seller_copilot_state import SellerCopilotState


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
    return "refinement_node"


def build_seller_copilot_graph():
    graph = StateGraph(SellerCopilotState)

    graph.add_node("product_identity_node", product_identity_node)
    graph.add_node("clarification_node", clarification_node)
    graph.add_node("market_intelligence_node", market_intelligence_node)
    graph.add_node("pricing_strategy_node", pricing_strategy_node)
    graph.add_node("copywriting_node", copywriting_node)
    graph.add_node("validation_node", validation_node)
    graph.add_node("refinement_node", refinement_node)
    graph.add_node("package_builder_node", package_builder_node)

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
    graph.add_edge("package_builder_node", END)

    return graph.compile()


seller_copilot_graph = build_seller_copilot_graph()