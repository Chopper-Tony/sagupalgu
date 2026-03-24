"""
LangGraph 그래프 정의 — M2 단일 경로 버전.

그래프 책임: 상품 식별 → 시세 분석 → 가격 전략 → 카피라이팅 → 검증 → 패키지 빌드
게시(publish) / 복구(recovery) / 판매 후 최적화(post_sale)는
SessionService가 노드 함수를 직접 호출하여 처리.

노드 흐름:
START → product_identity → market_intelligence → pricing → copywriting
     → validation → (refinement 루프) → package_builder → END
"""
from __future__ import annotations


# ── 그래프 빌더 ────────────────────────────────────────────────────

def build_seller_copilot_graph():
    from langgraph.graph import END, START, StateGraph  # lazy import

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
    from app.graph.routing import route_after_product_identity, route_after_validation
    from app.graph.seller_copilot_state import SellerCopilotState

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
    graph.add_edge("package_builder_node", END)  # 그래프 종료 — 게시는 SessionService 담당

    return graph.compile()


# lazy 빌드 — 모듈 import 시점에 langgraph가 없어도 통과
_compiled_graph = None


def _get_compiled_graph():
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_seller_copilot_graph()
    return _compiled_graph


# 하위 호환: 기존 코드에서 seller_copilot_graph.invoke() 하던 것 유지
class _LazyGraphProxy:
    """seller_copilot_graph.invoke() 호출을 lazy 빌드로 연결."""
    def invoke(self, *args, **kwargs):
        return _get_compiled_graph().invoke(*args, **kwargs)

    def __getattr__(self, name):
        return getattr(_get_compiled_graph(), name)


seller_copilot_graph = _LazyGraphProxy()
