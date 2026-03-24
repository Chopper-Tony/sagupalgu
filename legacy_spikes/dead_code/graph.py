from typing import Literal
from langgraph.graph import StateGraph, START, END
from app.state.sell_session_state import SellSessionState
from app.graph.nodes import (
    preprocess_node,
    product_identity_node,
    market_intelligence_node,
    pricing_node,
    copywriting_node,
    validation_node,
)

def route_after_product_identity(state: SellSessionState) -> Literal["end_waiting_confirmation"]:
    return "end_waiting_confirmation"

def route_after_validation(state: SellSessionState) -> Literal["end_waiting_publish"]:
    return "end_waiting_publish"

def build_graph():
    graph = StateGraph(SellSessionState)

    graph.add_node("preprocess", preprocess_node)
    graph.add_node("product_identity", product_identity_node)
    graph.add_node("market_intelligence", market_intelligence_node)
    graph.add_node("pricing", pricing_node)
    graph.add_node("copywriting", copywriting_node)
    graph.add_node("validation", validation_node)

    graph.add_edge(START, "preprocess")
    graph.add_edge("preprocess", "product_identity")
    graph.add_conditional_edges(
        "product_identity",
        route_after_product_identity,
        {"end_waiting_confirmation": END},
    )

    # NOTE:
    # 상품 확정 이후에는 graph를 다시 이어서 실행하는 방식으로 가정한다.
    # 즉, 첫 번째 graph run은 상품 확인 전까지.
    return graph.compile()

def build_post_confirmation_graph():
    graph = StateGraph(SellSessionState)

    graph.add_node("market_intelligence", market_intelligence_node)
    graph.add_node("pricing", pricing_node)
    graph.add_node("copywriting", copywriting_node)
    graph.add_node("validation", validation_node)

    graph.add_edge(START, "market_intelligence")
    graph.add_edge("market_intelligence", "pricing")
    graph.add_edge("pricing", "copywriting")
    graph.add_edge("copywriting", "validation")
    graph.add_conditional_edges(
        "validation",
        route_after_validation,
        {"end_waiting_publish": END},
    )
    return graph.compile()
