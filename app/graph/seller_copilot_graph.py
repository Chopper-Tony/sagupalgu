"""
LangGraph 그래프 정의.

그래프 책임: 상품 식별 → 시세 분석 → 가격 전략 → 카피라이팅 → critic → validation → 패키지 빌드
게시(publish) / 복구(recovery) / 판매 후 최적화(post_sale)는
SessionService가 노드 함수를 직접 호출하여 처리.

PR2 변경:
  - critic이 Routing Agent로 승격되어 routing.py가 단순 dispatch.
    repair_action에 따라 6갈래로 분기 (pass / rewrite / reprice / clarify / replan).
  - refinement_node가 validation_node에 흡수되어 그래프에서 제거.

PR3 변경:
  - planner Strategy Agent가 정책 4필드 결정. market_depth='skip' 가드 분기.
  - clarification 통합 노드 (clarification_node.py).

PR4-cleanup:
  - 모든 노드 등록 이름을 Target Architecture 정식 이름으로 (PR1 알리아스 흡수).
    product_gate_node / pricing_rule_node / validation_rules_node / post_sale_policy_node.
  - clarification_node 단일 entry point만 등록 (legacy stub 제거).
"""
from __future__ import annotations


# ── 그래프 빌더 ────────────────────────────────────────────────────

def build_seller_copilot_graph():
    from langgraph.graph import END, START, StateGraph  # lazy import

    from app.graph.nodes.clarification_node import clarification_node
    from app.graph.nodes.copywriting_agent import copywriting_node
    from app.graph.nodes.critic_agent import listing_critic_node
    from app.graph.nodes.market_agent import market_intelligence_node, pricing_rule_node
    from app.graph.nodes.packaging_agent import package_builder_node
    from app.graph.nodes.planner_agent import mission_planner_node
    from app.graph.nodes.product_agent import product_gate_node
    from app.graph.nodes.validation_agent import validation_rules_node
    from app.graph.routing import (
        route_after_critic,
        route_after_pre_listing_clarification,
        route_after_product_identity,
    )
    from app.graph.seller_copilot_state import SellerCopilotState

    graph = StateGraph(SellerCopilotState)

    # ── 노드 등록 (PR4-cleanup: 정식 이름) ────────────────────────
    # clarification_node가 product 식별 단계 + pre_listing 단계 모두 담당 (state로 모드 분기).
    # product_identity 후 conditional edge에서 두 시점에 모두 호출.
    graph.add_node("product_gate_node", product_gate_node)
    graph.add_node("clarification_node", clarification_node)
    graph.add_node("market_intelligence_node", market_intelligence_node)
    graph.add_node("pricing_rule_node", pricing_rule_node)
    graph.add_node("copywriting_node", copywriting_node)
    graph.add_node("validation_rules_node", validation_rules_node)
    graph.add_node("package_builder_node", package_builder_node)
    graph.add_node("listing_critic_node", listing_critic_node)
    graph.add_node("mission_planner_node", mission_planner_node)

    # ── 메인 플로우 ──────────────────────────────────────────────
    graph.add_edge(START, "mission_planner_node")
    graph.add_edge("mission_planner_node", "product_gate_node")

    # product_gate → (needs_user_input: clarification(product 모드) / 충분: clarification(pre_listing 모드))
    # 통합 clarification_node가 state로 모드 자동 분기. routing.py 반환값을
    # "pre_listing_clarification_node" (legacy)에서 "clarification_node"로 매핑.
    graph.add_conditional_edges(
        "product_gate_node",
        route_after_product_identity,
        {
            "clarification_node": "clarification_node",
            "pre_listing_clarification_node": "clarification_node",
        },
    )

    # clarification → (needs_user_input: END 사용자 답변 대기 / 충분: market 또는 pricing_skip)
    graph.add_conditional_edges(
        "clarification_node",
        route_after_pre_listing_clarification,
        {
            "market_intelligence_node": "market_intelligence_node",
            "pricing_rule_node": "pricing_rule_node",
            "__end__": END,
        },
    )

    graph.add_edge("market_intelligence_node", "pricing_rule_node")
    graph.add_edge("pricing_rule_node", "copywriting_node")
    graph.add_edge("copywriting_node", "listing_critic_node")

    # ── PR2: Critic Routing Agent → 6갈래 dispatch ───────────────
    graph.add_conditional_edges(
        "listing_critic_node",
        route_after_critic,
        {
            "validation_rules_node": "validation_rules_node",
            "copywriting_node": "copywriting_node",
            "pricing_rule_node": "pricing_rule_node",
            "clarification_node": "clarification_node",
            "mission_planner_node": "mission_planner_node",
        },
    )

    # ── PR2: refinement 노드 제거 ─────────────────────────────────
    graph.add_edge("validation_rules_node", "package_builder_node")
    graph.add_edge("package_builder_node", END)

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
