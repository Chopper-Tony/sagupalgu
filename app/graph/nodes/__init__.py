"""
app.graph.nodes 패키지 — 에이전트별 노드 모듈.

하위 호환을 위해 seller_copilot_nodes.py가 이 패키지에서 re-export.
"""
from app.graph.nodes.product_agent import (
    product_gate_node,        # PR1 알리아스: product_identity_node
    product_identity_node,
)
from app.graph.nodes.market_agent import (
    market_intelligence_node,
    pricing_rule_node,        # PR1 알리아스: pricing_strategy_node
    pricing_strategy_node,
)
from app.graph.nodes.copywriting_agent import (
    _build_template_listing,
    copywriting_node,
    refinement_node,
)
# PR3 통합: clarification_node는 새 단일 entry point에서 가져온다.
# product_agent.clarification_node와 clarification_listing_agent.pre_listing_clarification_node는
# 모두 이 통합 함수로 위임되는 deprecated wrapper.
from app.graph.nodes.clarification_node import clarification_node
from app.graph.nodes.clarification_listing_agent import pre_listing_clarification_node
from app.graph.nodes.critic_agent import listing_critic_node
from app.graph.nodes.planner_agent import mission_planner_node
from app.graph.nodes.validation_agent import (
    validation_node,
    validation_rules_node,    # PR1 알리아스: validation_node
)
from app.graph.nodes.recovery_agent import recovery_node
from app.graph.nodes.packaging_agent import package_builder_node, publish_node
from app.graph.nodes.optimization_agent import (
    post_sale_optimization_node,
    post_sale_policy_node,    # PR1 알리아스: post_sale_optimization_node
)
from app.graph.nodes.helpers import (
    _build_react_llm,
    _extract_market_context,
    _log,
    _record_error,
    _record_tool_call,
    _run_async,
    _safe_int,
)

__all__ = [
    # Agent 1
    "product_identity_node",
    "product_gate_node",          # PR1 알리아스 (Target: Deterministic Node)
    "clarification_node",
    # Agent 2
    "market_intelligence_node",
    "pricing_strategy_node",
    "pricing_rule_node",          # PR1 알리아스 (Target: Deterministic Node)
    # Agent 3
    "copywriting_node",
    "refinement_node",
    "_build_template_listing",
    # Agent 0 (Planner)
    "mission_planner_node",
    # Agent 6 (Critic)
    "listing_critic_node",
    # Agent 4
    "validation_node",
    "validation_rules_node",      # PR1 알리아스 (Target: Deterministic Node + refinement 흡수)
    "recovery_node",
    # Packaging
    "package_builder_node",
    "publish_node",
    # Agent 5
    "post_sale_optimization_node",
    "post_sale_policy_node",      # PR1 알리아스 (Target: Deterministic Node)
    # Helpers
    "_log",
    "_record_tool_call",
    "_record_error",
    "_safe_int",
    "_run_async",
    "_build_react_llm",
    "_extract_market_context",
]
