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

PR3 변경:
  - planner Strategy Agent가 결정한 market_depth를 보고 시세 단계를 skip할지 결정.
  - skip은 _skip_allowed() 가드를 통과해야만 실제 적용 (남용 차단).
  - 미통과 시 silent crawl_only fallback + skip_rejected_reason 기록.
"""
from __future__ import annotations

from typing import Optional, Tuple

from app.domain.critic_policy import LOW_RISK_SKIP_CATEGORIES, MAX_PLAN_REVISIONS
from app.graph.seller_copilot_state import SellerCopilotState

MAX_VALIDATION_RETRIES = 2


def route_after_product_identity(state: SellerCopilotState) -> str:
    if state.get("needs_user_input", False):
        return "clarification_node"
    return "pre_listing_clarification_node"


def route_after_pre_listing_clarification(state: SellerCopilotState) -> str:
    """정보 부족이면 END (사용자 답변 대기), 충분하면 market_depth 정책에 따라 분기.

    PR3 변경: market_depth='skip' + _skip_allowed() 통과 시 pricing으로 직진.
    그렇지 않으면 market_intelligence_node. route_after_planner와 동일 로직 위임.
    """
    if state.get("needs_user_input", False) and not state.get("pre_listing_done", False):
        return "__end__"
    return route_after_planner(state)


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


def route_after_planner(state: SellerCopilotState) -> str:
    """planner 후 분기 — market_depth='skip'이면 _skip_allowed() 가드를 통과해야 시세 건너뜀.

    PR3 신규.
    skip은 다음 조건 중 하나 이상 충족 시만 허용 (남용 방지):
      1. 사용자가 가격을 명시 입력 (user_product_input.price)
      2. 이전 market_context가 잔존 (replan 케이스)
      3. plan_mode='shallow' AND 카테고리가 LOW_RISK_SKIP_CATEGORIES

    미충족 시 silent crawl_only로 강등 + skip_rejected_reason 기록.
    이는 planner LLM이 근거 없이 skip을 선택해도 안전망이 있다는 보장.
    """
    depth = state.get("market_depth", "crawl_plus_rag")
    if depth != "skip":
        # planner가 skip을 시도하지 않은 경우. skip_attempted=False (default 유지).
        return "market_intelligence_node"

    # CTO PR3 #2: planner가 skip을 시도했음을 기록 (시도 안 함 vs 시도+거절 구분).
    state["skip_attempted"] = True

    allowed, reason = _skip_allowed(state)
    if not allowed:
        # silent fallback: skip → crawl_only로 강등
        state["market_depth"] = "crawl_only"
        state["skip_rejected_reason"] = reason
        state.setdefault("debug_logs", []).append(f"routing:skip_rejected reason={reason} → crawl_only")
        return "market_intelligence_node"

    # skip 허용 — 시세 단계 건너뛰고 pricing으로 직진
    state.setdefault("debug_logs", []).append("routing:skip_allowed → pricing_strategy_node")
    return "pricing_strategy_node"


def _skip_allowed(state: SellerCopilotState) -> Tuple[bool, Optional[str]]:
    """market_depth='skip' 허용 여부 + 미허용 사유.

    조건 1: 사용자가 가격을 명시 입력
    조건 2: 이전 market_context가 잔존 (replan)
    조건 3: plan_mode='shallow' AND 카테고리가 LOW_RISK_SKIP_CATEGORIES
    """
    user_input = state.get("user_product_input") or {}
    if user_input.get("price"):
        return True, None

    if state.get("market_context"):
        return True, None

    plan_mode = state.get("plan_mode", "balanced")
    category = (state.get("confirmed_product") or {}).get("category", "")
    if plan_mode == "shallow" and category in LOW_RISK_SKIP_CATEGORIES:
        return True, None

    return False, "no_user_price_no_prev_context_not_low_risk_shallow"


def route_after_validation(state: SellerCopilotState) -> str:
    """validation 후 분기.

    PR2 변경:
      - refinement_node가 validation_rules 내부로 흡수되어 사라졌다.
      - validation_rules가 자동 보강 가능하면 내부에서 보강 후 재검증 → pass.
      - 보강 불가능이면 repair_action_hint를 남겨두는데, 이는 다음 critic이 참조한다.
      - 따라서 여기서는 단순히 package_builder로 직진한다.
    """
    return "package_builder_node"
