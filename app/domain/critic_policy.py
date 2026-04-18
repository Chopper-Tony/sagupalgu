"""
Critic / Planner / Routing 정책 상수 단일 원천.

PR1에서는 모듈만 신규 생성. 기존 routing.py·critic_agent.py의 동일 상수는
PR2에서 이 모듈로 이전한다 (PR1 "동작 변화 0" 원칙 유지).

이 모듈은 라우팅 결정 자체를 담지 않는다 (그건 routing.py의 역할).
여기 모인 상수들은 critic 프롬프트 가이드라인, planner 정책 조합 제약,
그리고 다운스트림 노드들이 참조하는 결정론적 임계값이다.
"""
from __future__ import annotations

from typing import Dict, FrozenSet, List


# ── critic 프롬프트 가이드라인 ────────────────────────────────────────
# PR2 이후 critic은 score 대신 repair_action으로 라우팅한다.
# 이 임계값은 라우팅 결정에 쓰지 않고, critic 프롬프트에
# "70 이상이면 통과 수준" 같은 가이드라인으로만 주입한다.
CRITIC_PASS_THRESHOLD: int = 70


# ── 루프 상한 ─────────────────────────────────────────────────────────
# replan 무한 루프 방지. PR2 routing dispatch가 이 값을 보고
# 도달 시 강제로 validation_rules로 보낸다 (failure_mode 기록 포함).
MAX_PLAN_REVISIONS: int = 2

# rewrite 재시도 상한. 현재 SellerCopilotState.max_critic_retries 기본값과 일치.
MAX_CRITIC_RETRIES: int = 2


# ── plan_mode × critic_policy 조합 제약 ──────────────────────────────
# planner가 정책을 결정할 때 모순 조합을 피하도록 프롬프트에 주입.
# 예: shallow + strict = "빠르게 가자면서 엄격하게 평가" 라는 모순.
POLICY_COMBO_RULES: Dict[str, Dict[str, List[str]]] = {
    "shallow": {"critic_policy": ["minimal", "normal"]},
    "balanced": {"critic_policy": ["minimal", "normal", "strict"]},
    "deep": {"critic_policy": ["normal", "strict"]},
}


# ── market_depth=skip 허용 카테고리 ──────────────────────────────────
# planner가 market 단계를 건너뛰려고 할 때, _skip_allowed() 가드가
# 이 set만을 참조한다. 프롬프트에 카테고리 목록을 하드코딩하면
# 일관성·테스트·운영 추적이 무너지므로 도메인 상수로 박는다.
LOW_RISK_SKIP_CATEGORIES: FrozenSet[str] = frozenset({
    "clothing",
    "daily_goods",
    "books",
    "small_accessories",
})
