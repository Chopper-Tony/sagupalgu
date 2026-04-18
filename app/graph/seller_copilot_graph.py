"""
LangGraph 그래프 정의.

그래프 책임: 상품 식별 → 시세 분석 → 가격 전략 → 카피라이팅 → critic → validation → 패키지 빌드
게시(publish) / 복구(recovery) / 판매 후 최적화(post_sale)는
SessionService가 노드 함수를 직접 호출하여 처리.

PR2 변경:
  - critic이 Routing Agent로 승격되어 routing.py가 단순 dispatch.
    repair_action에 따라 6갈래로 분기 (pass / rewrite / reprice / clarify / replan).
  - refinement_node가 validation_node에 흡수되어 그래프에서 제거.
    validation 후에는 단순히 package_builder로 직진 (보강은 validation 내부에서).
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
        validation_node,
    )
    from app.graph.nodes.clarification_listing_agent import pre_listing_clarification_node
    from app.graph.nodes.critic_agent import listing_critic_node
    from app.graph.nodes.planner_agent import mission_planner_node
    from app.graph.routing import (
        route_after_critic,
        route_after_pre_listing_clarification,
        route_after_product_identity,
    )
    from app.graph.seller_copilot_state import SellerCopilotState

    graph = StateGraph(SellerCopilotState)

    # 노드 등록
    graph.add_node("product_identity_node", product_identity_node)
    graph.add_node("clarification_node", clarification_node)
    graph.add_node("market_intelligence_node", market_intelligence_node)
    graph.add_node("pricing_strategy_node", pricing_strategy_node)
    graph.add_node("copywriting_node", copywriting_node)
    graph.add_node("validation_node", validation_node)
    graph.add_node("package_builder_node", package_builder_node)
    graph.add_node("listing_critic_node", listing_critic_node)
    graph.add_node("mission_planner_node", mission_planner_node)
    graph.add_node("pre_listing_clarification_node", pre_listing_clarification_node)

    # ── 메인 플로우 ──────────────────────────────────────────────
    graph.add_edge(START, "mission_planner_node")
    graph.add_edge("mission_planner_node", "product_identity_node")

    graph.add_conditional_edges(
        "product_identity_node",
        route_after_product_identity,
        {
            "clarification_node": "clarification_node",
            "pre_listing_clarification_node": "pre_listing_clarification_node",
        },
    )

    graph.add_edge("clarification_node", END)

    # Pre-listing clarification → (충분: market 또는 pricing_skip / 부족: END)
    # PR3: route_after_pre_listing_clarification이 내부적으로 route_after_planner를 호출,
    # market_depth='skip' + _skip_allowed() 통과 시 pricing_strategy_node로 직진.
    graph.add_conditional_edges(
        "pre_listing_clarification_node",
        route_after_pre_listing_clarification,
        {
            "market_intelligence_node": "market_intelligence_node",
            "pricing_strategy_node": "pricing_strategy_node",
            "__end__": END,
        },
    )

    graph.add_edge("market_intelligence_node", "pricing_strategy_node")
    graph.add_edge("pricing_strategy_node", "copywriting_node")
    graph.add_edge("copywriting_node", "listing_critic_node")

    # ── PR2: Critic Routing Agent → 6갈래 dispatch ───────────────
    # repair_action별 매핑:
    #   pass      → validation
    #   rewrite_* → copywriting
    #   reprice   → pricing (가격 재산정 후 copywriting)
    #   clarify   → clarification (END 후 사용자 답변 대기)
    #   replan    → planner (plan 수정 후 처음부터)
    graph.add_conditional_edges(
        "listing_critic_node",
        route_after_critic,
        {
            "validation_node": "validation_node",
            "copywriting_node": "copywriting_node",
            "pricing_strategy_node": "pricing_strategy_node",
            "clarification_node": "clarification_node",
            "mission_planner_node": "mission_planner_node",
        },
    )

    # ── PR2: refinement 노드 제거 ─────────────────────────────────
    # validation은 자동 보강을 내부에서 처리. 외부 분기 없이 package로 직진.
    graph.add_edge("validation_node", "package_builder_node")
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
