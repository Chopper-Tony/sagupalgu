"""
Single source of truth for the agentic decision graph policy.

이 모듈은 다음 3가지의 단일 원천이다:
  - PR2: critic Routing Agent의 라우팅 정책 (repair_action 분기 상한)
  - PR3: planner Strategy Agent의 정책 조합 제약
  - PR3: route_after_planner의 market skip 가드 + 카테고리 화이트리스트

여기 모인 상수들을 routing.py·critic_agent·planner_agent·state 초기화에서
모두 import해서 쓴다. 정책이 여러 모듈에 흩어지면 일관성·테스트·운영 추적이
무너지므로, 변경은 반드시 이 파일을 통해서만 한다.

라우팅 결정 자체는 routing.py가 담당하고, 이 모듈은 그 결정에 쓰일
임계값·상한·기본값·화이트리스트만 제공한다.
"""
from __future__ import annotations

from typing import Dict, FrozenSet, List


# ── critic 프롬프트 가이드라인 ────────────────────────────────────────
# PR2 이후 critic은 score 대신 repair_action으로 라우팅한다.
# 이 임계값은 라우팅 결정에 직접 쓰이지 않고, critic 프롬프트에
# "70 이상이면 통과 수준" 같은 가이드라인으로만 주입한다.
# critic_policy ("minimal" | "normal" | "strict")로 엄격도가 동적으로 바뀐다.
CRITIC_PASS_THRESHOLD: int = 70


# ── 루프 상한 ─────────────────────────────────────────────────────────
# replan 무한 루프 방지. PR2 routing dispatch가 이 값을 보고
# 도달 시 강제로 validation_rules로 보낸다 (failure_mode="replan_limit_reached" 기록).
#
# 2회로 정한 근거:
#   - 1회: 첫 플랜이 명백히 틀렸을 때 수정 기회
#   - 2회: 수정된 플랜도 실패했을 때 마지막 시도
#   - 3회 이상은 근본적 입력 문제로 판단 → critic 강제 pass + safety net
MAX_PLAN_REVISIONS: int = 2

# rewrite 재시도 상한. 현재 SellerCopilotState.max_critic_retries 기본값과 일치.
# 2회 초과 시 critic은 강제 pass로 빠진다 (CRITIC_PASS_THRESHOLD와 무관).
MAX_CRITIC_RETRIES: int = 2


# ── plan_mode × critic_policy 조합 제약 ──────────────────────────────
# planner가 정책을 결정할 때 모순 조합을 피하도록 프롬프트에 주입.
#
# 정규화 기준 (CTO PR3 #3):
#   - shallow는 strict critic과 함께 사용할 수 없다
#     ("빠르게 가자면서 엄격하게 평가" → critic이 매번 reject → shallow 의도 무력화).
#   - deep은 minimal critic과 함께 사용할 수 없다
#     (심층 분석을 했는데 평가가 관대하면 분석 비용 낭비).
#   - 위반 조합은 안정성을 위해 normal로 강등 (양쪽 plan_mode 모두에서 허용된 안전값).
POLICY_COMBO_RULES: Dict[str, Dict[str, List[str]]] = {
    "shallow": {"critic_policy": ["minimal", "normal"]},
    "balanced": {"critic_policy": ["minimal", "normal", "strict"]},
    "deep": {"critic_policy": ["normal", "strict"]},
}


# ── market_depth 제어 범위 (CTO PR3 #5: 3단 유지 원칙) ───────────────
# planner가 시세 조사 강도를 결정. market_intelligence_node는 이를 그대로 따른다.
# 이 3단 구조를 확장하지 말 것 (예: "crawl_full", "rag_only" 등 추가 금지).
# 추가 깊이가 필요하면 market_depth가 아니라 다른 정책 필드(예: rag_top_k)로 분리.
#
# 3단 의미:
#   - skip:           시세 단계 건너뛰고 pricing으로 직진 (routing 가드 통과 시만)
#   - crawl_only:     실시간 크롤링만, RAG 도구 bind 제외 (빠른 시세)
#   - crawl_plus_rag: 기본. 크롤링 + sample_count<3 시 RAG 보완
#
# 통제력: planner가 깊이 결정 → market은 따른다. 다른 노드가 market_depth를
# 임의로 override하면 planner의 통제력이 약화되므로 금지.
VALID_MARKET_DEPTHS = ("skip", "crawl_only", "crawl_plus_rag")


# ── market_depth=skip 허용 카테고리 ──────────────────────────────────
# planner가 market 단계를 건너뛰려고 할 때, _skip_allowed() 가드가
# 이 set만을 참조한다. 프롬프트에 카테고리 목록을 하드코딩하면
# 일관성·테스트·운영 추적이 무너지므로 도메인 상수로 박는다.
#
# Low-risk 기준 (확장 시 동일 기준 적용):
#   1. 가격 변동성이 낮음 (시세 조사 안 해도 적정 가격 추정 가능)
#   2. 품목 특성이 명확 (모델·옵션 분기가 적음)
#   3. 중고거래 사기·진품 확인 리스크가 낮음
#
# 의도적 제외:
#   - electronics: 가격 변동 + 진품 확인 필요
#   - cosmetics:   유통기한 + 진품 리스크
#   - luxury_goods: 진품 검증 필수
LOW_RISK_SKIP_CATEGORIES: FrozenSet[str] = frozenset({
    "clothing",
    "daily_goods",
    "books",
    "small_accessories",
})


# ── State baseline 기본값 (단일 원천) ─────────────────────────────────
# state 초기화 / planner fallback / 테스트 baseline 모두 이 상수만 참조.
# 같은 값이 여러 곳에 흩어지면 정책 변경 시 누락 위험.
DEFAULT_PLAN_MODE: str = "balanced"
DEFAULT_MARKET_DEPTH: str = "crawl_plus_rag"
DEFAULT_CRITIC_POLICY: str = "normal"
DEFAULT_CLARIFICATION_POLICY: str = "ask_early"

# repair_action 기본값을 "pass"로 둬서 critic이 한 번도 실행되지 않은
# state에 대해서도 routing이 안전하게 동작하도록 한다 (PR2 route_after_critic
# 의 fallback `state.get("repair_action", "pass")`와 의미 정렬).
DEFAULT_REPAIR_ACTION: str = "pass"
