"""
그래프 라우터 함수 — langgraph 의존성 없음.

순수 상태 기반 분기 로직만 담당.
seller_copilot_graph.py의 StateGraph가 이 함수들을 조건부 엣지로 등록.
테스트는 langgraph 없이 이 모듈만 import해서 unit 수준으로 검증 가능.

PR2 변경:
  - critic 분기는 score 임계값이 아니라 state.repair_action을 직접 본다 (단순 dispatch).
  - critic Routing Agent가 repair_action·failure_mode·rewrite_plan을 결정,
    여기서는 그 결정을 노드 이름으로 매핑만 한다.
  - 임계값 상수는 app/domain/critic_policy.py로 단일 원천화 (중복 제거).
"""
from __future__ import annotations

from app.domain.critic_policy import MAX_PLAN_REVISIONS
from app.graph.seller_copilot_state import SellerCopilotState

MAX_VALIDATION_RETRIES = 2


def route_after_product_identity(state: SellerCopilotState) -> str:
    if state.get("needs_user_input", False):
        return "clarification_node"
    return "pre_listing_clarification_node"


def route_after_pre_listing_clarification(state: SellerCopilotState) -> str:
    """정보 부족이면 END (사용자 답변 대기), 충분하면 market으로."""
    if state.get("needs_user_input", False) and not state.get("pre_listing_done", False):
        return "__end__"
    return "market_intelligence_node"


def route_after_critic(state: SellerCopilotState) -> str:
    """critic Routing Agent가 결정한 repair_action을 노드 이름으로 단순 dispatch.

    repair_action 값:
      - "pass":               validation_rules로 진행
      - "rewrite_*":          copywriting (rewrite_title / rewrite_description / rewrite_full)
      - "reprice":            pricing_rule로 되돌아가 가격 재조정
      - "clarify":            clarification으로 보내 사용자에게 추가 정보 요청
      - "replan":             mission_planner로 돌아가 plan 수정

    안전망:
      - replan을 요청했더라도 plan_revision_count >= MAX_PLAN_REVISIONS면
        강제로 validation_rules로 진입 (failure_mode='replan_limit_reached' 기록).
      - critic이 한 번도 실행되지 않은 state는 repair_action 기본값 "pass"
        (app/domain/critic_policy.py:DEFAULT_REPAIR_ACTION) 덕에 validation_rules로 빠짐.
      - 알 수 없는 repair_action도 validation_rules safety net으로 (critic이 라우팅을 못
        정한 경우와 동일 처리).
    """
    action = state.get("repair_action", "pass")

    # replan 무한 루프 차단 — 상한 도달 시 강제 통과 + 관측 가능하게 흔적 남김
    if action == "replan" and int(state.get("plan_revision_count") or 0) >= MAX_PLAN_REVISIONS:
        state["failure_mode"] = "replan_limit_reached"
        state.setdefault("debug_logs", []).append("routing:replan_limit_reached → validation_rules")
        return "validation_node"

    if action == "pass":
        return "validation_node"
    if action.startswith("rewrite"):
        return "copywriting_node"
    if action == "reprice":
        return "pricing_strategy_node"
    if action == "clarify":
        return "clarification_node"
    if action == "replan":
        return "mission_planner_node"

    # 알 수 없는 repair_action — critic_parse_error 같은 fallback과 동일 안전망
    return "validation_node"


def route_after_validation(state: SellerCopilotState) -> str:
    """validation 후 분기.

    PR2 변경:
      - refinement_node가 validation_rules 내부로 흡수되어 사라졌다.
      - validation_rules가 자동 보강 가능하면 내부에서 보강 후 재검증 → pass.
      - 보강 불가능이면 repair_action_hint를 남겨두는데, 이는 다음 critic이 참조한다.
      - 따라서 여기서는 단순히 package_builder로 직진한다.
    """
    return "package_builder_node"
