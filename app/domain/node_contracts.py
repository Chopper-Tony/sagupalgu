"""
노드별 output contract 정의.

각 노드가 실행 후 반드시 state에 남겨야 하는 key를 정의한다.
tests/test_node_contracts.py에서 이 계약을 검증한다.

계약 형식:
  "required": 반드시 존재해야 하는 키 목록
  "one_of":   OR 조건 — 하위 목록 중 하나 이상의 그룹이 모두 존재해야 함
"""
from __future__ import annotations

from typing import Any, Dict, List

NodeContract = Dict[str, Any]

NODE_OUTPUT_CONTRACTS: Dict[str, NodeContract] = {
    "mission_planner_node": {
        "required": ["mission_goal", "plan", "decision_rationale", "missing_information"],
    },
    "product_identity_node": {
        "required": ["checkpoint", "status"],
        "one_of": [["confirmed_product"], ["needs_user_input"]],
    },
    "pre_listing_clarification_node": {
        "required": ["pre_listing_done", "pre_listing_questions", "missing_information"],
    },
    "market_intelligence_node": {
        "required": ["market_context", "checkpoint"],
    },
    "pricing_strategy_node": {
        "required": ["strategy", "checkpoint"],
    },
    "copywriting_node": {
        "required": ["canonical_listing", "checkpoint", "status"],
    },
    "listing_critic_node": {
        "required": ["critic_score", "critic_feedback", "critic_rewrite_instructions"],
    },
    "validation_node": {
        "required": ["validation_passed", "validation_result", "checkpoint"],
    },
    "package_builder_node": {
        "required": ["platform_packages", "checkpoint", "status"],
    },
}


def check_contract(node_name: str, state: Dict[str, Any]) -> List[str]:
    """계약 위반 키 목록을 반환한다. 빈 리스트면 통과."""
    contract = NODE_OUTPUT_CONTRACTS.get(node_name)
    if not contract:
        return [f"unknown node: {node_name}"]

    violations = []

    for key in contract.get("required", []):
        if key not in state or state[key] is None:
            violations.append(f"missing required key: {key}")

    one_of = contract.get("one_of")
    if one_of:
        satisfied = any(
            all(k in state and state[k] is not None for k in group)
            for group in one_of
        )
        if not satisfied:
            violations.append(f"none of one_of groups satisfied: {one_of}")

    return violations
