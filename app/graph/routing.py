"""
그래프 라우터 함수 — langgraph 의존성 없음.

순수 상태 기반 분기 로직만 담당.
seller_copilot_graph.py의 StateGraph가 이 함수들을 조건부 엣지로 등록.
테스트는 langgraph 없이 이 모듈만 import해서 unit 수준으로 검증 가능.
"""
from __future__ import annotations

from app.graph.seller_copilot_state import SellerCopilotState

MAX_VALIDATION_RETRIES = 2
CRITIC_PASS_THRESHOLD = 70
MAX_CRITIC_RETRIES = 2
MAX_REPLANS = 1


def route_after_product_identity(state: SellerCopilotState) -> str:
    if state.get("needs_user_input", False):
        return "clarification_node"
    return "market_intelligence_node"


def route_after_critic(state: SellerCopilotState) -> str:
    """critic 평가 후 3갈래 분기: pass / rewrite / replan."""
    score = int(state.get("critic_score") or 0)
    retry_count = int(state.get("critic_retry_count") or 0)
    max_retries = int(state.get("max_critic_retries") or MAX_CRITIC_RETRIES)
    plan_revision = int(state.get("plan_revision_count") or 0)
    max_replans = int(state.get("max_replans") or MAX_REPLANS)

    if score >= CRITIC_PASS_THRESHOLD:
        return "validation_node"

    # rewrite 가능하면 rewrite
    if retry_count < max_retries and state.get("rewrite_instruction"):
        return "copywriting_node"

    # rewrite 한도 초과 → replan 가능하면 replan
    if retry_count >= max_retries and plan_revision < max_replans:
        return "mission_planner_node"

    # 모두 한도 초과 → 강제 통과
    return "validation_node"


def route_after_validation(state: SellerCopilotState) -> str:
    if state.get("validation_passed", False):
        return "package_builder_node"
    retry = int(state.get("validation_retry_count") or 0)
    if retry >= MAX_VALIDATION_RETRIES:
        return "package_builder_node"
    return "refinement_node"
