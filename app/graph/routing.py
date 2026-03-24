"""
그래프 라우터 함수 — langgraph 의존성 없음.

순수 상태 기반 분기 로직만 담당.
seller_copilot_graph.py의 StateGraph가 이 함수들을 조건부 엣지로 등록.
테스트는 langgraph 없이 이 모듈만 import해서 unit 수준으로 검증 가능.
"""
from __future__ import annotations

from app.graph.seller_copilot_state import SellerCopilotState

MAX_VALIDATION_RETRIES = 2


def route_after_product_identity(state: SellerCopilotState) -> str:
    if state.get("needs_user_input", False):
        return "clarification_node"
    return "market_intelligence_node"


def route_after_validation(state: SellerCopilotState) -> str:
    if state.get("validation_passed", False):
        return "package_builder_node"
    retry = int(state.get("validation_retry_count") or 0)
    if retry >= MAX_VALIDATION_RETRIES:
        return "package_builder_node"
    return "refinement_node"
