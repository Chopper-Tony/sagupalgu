"""
Agent 0 — Mission Planner / Strategy Agent

분류 (Target Architecture, 4+2+5):
  mission_planner_node → Strategy Agent
                         LLM이 다음 4 정책 필드를 한 번에 결정 → 다운스트림 노드 동작
                         강도가 정책에 따라 동적으로 바뀐다.

정책 출력:
  plan_mode:            "shallow" | "balanced" | "deep"
                        깊이/공격성. shallow는 빠르고 가볍게, deep은 충실하게.
  market_depth:         "skip" | "crawl_only" | "crawl_plus_rag"
                        시세 조사 강도. skip은 routing.py의 _skip_allowed() 가드를
                        통과해야만 실제 적용된다.
  critic_policy:        "minimal" | "normal" | "strict"
                        critic 프롬프트 엄격도. plan_mode와 조합 제약이 있다
                        (POLICY_COMBO_RULES — shallow + strict 같은 모순 금지).
  clarification_policy: "ask_early" | "ask_late"
                        부족한 정보가 있을 때 사용자에게 질문하는 시점/개수.

기존 출력 (호환 유지):
  mission_goal: fast_sell | balanced | profit_max
  plan: {steps: [...], focus: str}
  decision_rationale: [str]
  missing_information: [str]

fallback baseline:
  LLM 실패 / 파싱 실패 시 critic_policy.DEFAULT_* (balanced/crawl_plus_rag/normal/ask_early)
  + 룰 기반 plan/missing — 현재 PR2 동작과 사실상 동등.
"""
from __future__ import annotations

import json
import re
from typing import Dict, List, Optional, Tuple

import logging

from app.domain.critic_policy import (
    DEFAULT_CLARIFICATION_POLICY,
    DEFAULT_CRITIC_POLICY,
    DEFAULT_MARKET_DEPTH,
    DEFAULT_PLAN_MODE,
    POLICY_COMBO_RULES,
)
from app.graph.seller_copilot_state import SellerCopilotState
from app.graph.nodes.helpers import (
    _build_react_llm,
    _log,
    _record_error,
    _record_node_timing,
    _run_async,
    _start_timer,
)


_VALID_PLAN_MODES = frozenset({"shallow", "balanced", "deep"})
_VALID_MARKET_DEPTHS = frozenset({"skip", "crawl_only", "crawl_plus_rag"})
_VALID_CRITIC_POLICIES = frozenset({"minimal", "normal", "strict"})
_VALID_CLARIFICATION_POLICIES = frozenset({"ask_early", "ask_late"})


def mission_planner_node(state: SellerCopilotState) -> SellerCopilotState:
    """세션 상태를 분석하고 4 정책 필드 + 실행 계획을 산출한다 (Strategy Agent)."""
    _timer = _start_timer()
    _log(state, "agent0:planner:start")

    is_replan = int(state.get("plan_revision_count") or 0) > 0
    if is_replan:
        _log(state, f"agent0:planner:replan revision={state['plan_revision_count']}")

    # ── LLM 기반 정책·계획 시도 ──────────────────────────────────────
    plan_result = _run_llm_planning(state, is_replan)
    if plan_result is None:
        plan_result = _rule_based_planning(state, is_replan)

    # mission_goal & plan & rationale & missing 적용
    state["plan"] = plan_result.get("plan", {})
    state["mission_goal"] = plan_result.get("mission_goal", state.get("mission_goal", "balanced"))
    state["decision_rationale"] = state.get("decision_rationale", []) + (plan_result.get("rationale") or [])
    state["missing_information"] = plan_result.get("missing_information") or []

    # ── 4 정책 필드 정규화 + 조합 제약 ─────────────────────────────
    policy = _normalize_and_constrain_policy(plan_result, state, is_replan)
    state["plan_mode"] = policy["plan_mode"]
    state["market_depth"] = policy["market_depth"]
    state["critic_policy"] = policy["critic_policy"]
    state["clarification_policy"] = policy["clarification_policy"]

    # ── mission_goal 기반 max_critic_retries 동적 (PR2까지 호환) ──
    goal = state["mission_goal"]
    if goal == "fast_sell":
        state["max_critic_retries"] = 1
    elif goal == "profit_max":
        state["max_critic_retries"] = 3
    else:
        state["max_critic_retries"] = 2

    _log(
        state,
        f"agent0:planner:done goal={goal} mode={policy['plan_mode']} "
        f"depth={policy['market_depth']} critic={policy['critic_policy']} "
        f"clarify={policy['clarification_policy']} steps={len(state['plan'].get('steps') or [])}",
    )
    _record_node_timing(state, "mission_planner", _timer)
    return state


# ── 정책 정규화 + 조합 제약 ────────────────────────────────────────


def _normalize_and_constrain_policy(
    plan_result: Dict, state: SellerCopilotState, is_replan: bool,
) -> Dict[str, str]:
    """LLM이 산출한 정책 4필드를 enum·조합 제약으로 강제 정규화."""
    plan_mode = _coerce(plan_result.get("plan_mode"), _VALID_PLAN_MODES, DEFAULT_PLAN_MODE)
    market_depth = _coerce(plan_result.get("market_depth"), _VALID_MARKET_DEPTHS, DEFAULT_MARKET_DEPTH)
    critic_policy = _coerce(plan_result.get("critic_policy"), _VALID_CRITIC_POLICIES, DEFAULT_CRITIC_POLICY)
    clarification_policy = _coerce(
        plan_result.get("clarification_policy"), _VALID_CLARIFICATION_POLICIES, DEFAULT_CLARIFICATION_POLICY,
    )

    # ── 조합 제약: shallow+strict 같은 모순은 normal로 강등 ───────
    allowed_critic = POLICY_COMBO_RULES.get(plan_mode, {}).get("critic_policy", [])
    if allowed_critic and critic_policy not in allowed_critic:
        _log(
            state,
            f"agent0:planner:combo_violation plan_mode={plan_mode} critic_policy={critic_policy} → normal",
        )
        critic_policy = "normal" if "normal" in allowed_critic else allowed_critic[0]

    # ── replan 시 critic 강화 ──────────────────────────────────────
    # 첫 시도가 실패한 케이스 → 기본보다 한 단계 strict 쪽으로 (allowed 안에서만).
    if is_replan and "strict" in allowed_critic and critic_policy == "minimal":
        critic_policy = "normal"

    return {
        "plan_mode": plan_mode,
        "market_depth": market_depth,
        "critic_policy": critic_policy,
        "clarification_policy": clarification_policy,
    }


def _coerce(value: Optional[str], valid: frozenset, default: str) -> str:
    if value is None:
        return default
    v = str(value).strip().lower()
    return v if v in valid else default


# ── LLM 호출 ──────────────────────────────────────────────────────────


def _run_llm_planning(state: SellerCopilotState, is_replan: bool) -> Optional[Dict]:
    """LLM이 mission_goal/plan + 4 정책 필드를 함께 결정."""
    try:
        llm = _build_react_llm()
        if llm is None:
            return None

        prompt = _build_planner_prompt(state, is_replan)

        from langchain_core.messages import HumanMessage
        result = _run_async(lambda: llm.ainvoke([HumanMessage(content=prompt)]))
        content = result.content if hasattr(result, "content") else str(result)

        return _parse_plan_response(content)
    except Exception as e:
        logging.getLogger(__name__).error("agent0 LLM planning failed", exc_info=True)
        _record_error(state, "mission_planner", f"LLM planning failed: {e}")
        _log(state, f"agent0:planner:llm_failed error={e}")
        return None


def _build_planner_prompt(state: SellerCopilotState, is_replan: bool) -> str:
    """플래너 프롬프트 — 4 정책 필드 결정 가이드 포함."""
    product = state.get("confirmed_product") or {}
    market = state.get("market_context") or {}
    critic_feedback = state.get("critic_feedback") or []
    user_input = state.get("user_product_input") or {}
    image_count = len(state.get("image_paths") or [])
    current_goal = state.get("mission_goal", "balanced")

    context_parts = [
        f"상품: {product.get('brand', '')} {product.get('model', '')} ({product.get('category', '')})",
        f"현재 목표: {current_goal}",
        f"이미지 수: {image_count}",
        f"사용자 입력 가격 명시 여부: {'yes' if user_input.get('price') else 'no'}",
    ]
    if market:
        context_parts.append(
            f"시장 데이터: 중앙값 {market.get('median_price', 0)}원, 샘플 {market.get('sample_count', 0)}개"
        )

    replan_context = ""
    if is_replan and critic_feedback:
        issues = [f"- [{f.get('type', '?')}] {f.get('reason', '')}" for f in critic_feedback[:3]]
        replan_context = (
            "\n\n이전 판매글 비평 결과:\n" + "\n".join(issues)
            + "\n위 문제를 해결하도록 계획을 수정하세요. "
            "이전 시도가 실패했으니 critic_policy를 한 단계 strict 쪽으로 조정하세요."
        )

    # POLICY_COMBO_RULES 텍스트화 — LLM이 모순 조합을 만들지 않도록
    combo_lines = []
    for pm, rule in POLICY_COMBO_RULES.items():
        allowed = rule.get("critic_policy", [])
        combo_lines.append(f"  - plan_mode={pm} → critic_policy ∈ {allowed}")
    combo_text = "\n".join(combo_lines)

    return f"""당신은 중고거래 판매 전략 + 워크플로우 정책 결정 에이전트입니다.
아래 상황을 분석하고 (1) 실행 계획 + (2) 다운스트림 노드들의 동작 정책을 JSON으로 결정하세요.

반드시 아래 형식으로만 응답 (다른 텍스트 금지):
{{
  "mission_goal": "fast_sell|balanced|profit_max",
  "plan": {{
    "steps": ["step1", "step2", ...],
    "focus": "핵심 전략 한 줄"
  }},
  "rationale": ["판단 근거1", "판단 근거2"],
  "missing_information": ["부족한 정보1", "부족한 정보2"],
  "plan_mode": "shallow|balanced|deep",
  "market_depth": "skip|crawl_only|crawl_plus_rag",
  "critic_policy": "minimal|normal|strict",
  "clarification_policy": "ask_early|ask_late"
}}

정책 필드 결정 가이드:
- plan_mode:
  shallow = 빠른 경로. 정보가 풍부하고 표준 상품일 때.
  balanced = 기본. 대부분의 케이스.
  deep = 정보가 부족하거나 모호할 때, 또는 replan 시.
- market_depth:
  skip = 사용자가 가격을 이미 입력했고 카테고리가 단순할 때만 (실제 적용은 routing 가드 통과 시).
  crawl_only = 빠른 시세만 필요할 때.
  crawl_plus_rag = 기본. 시세 + RAG 조합으로 충실한 가격 산정.
- critic_policy:
  minimal = 명백한 결함만. shallow와 어울림.
  normal = 균형. 대부분.
  strict = 사소한 결함도. deep과 어울림. replan 시 강화 후보.
- clarification_policy:
  ask_early = 정보가 부족하면 즉시 사용자에게 질문 (deep + 신뢰 중요할 때).
  ask_late = 가능한 한 자동 진행, 꼭 필요할 때만 질문 (shallow와 어울림).

조합 제약 (반드시 지켜야 함):
{combo_text}
- plan_mode=shallow + critic_policy=strict 같은 모순은 금지.

현재 상황:
{chr(10).join(context_parts)}
{replan_context}"""


def _parse_plan_response(content: str) -> Optional[Dict]:
    """LLM 응답에서 plan + 정책 JSON 추출. plan 키만 있어도 valid (legacy 호환)."""
    content = content.strip()
    if content.startswith("```"):
        content = re.sub(r"^```(?:json)?", "", content).strip()
        content = re.sub(r"```$", "", content).strip()
    try:
        data = json.loads(content)
        if isinstance(data, dict) and "plan" in data:
            return data
    except (json.JSONDecodeError, ValueError, TypeError):
        pass
    m = re.search(r"\{.*\}", content, re.DOTALL)
    if m:
        try:
            data = json.loads(m.group(0))
            if isinstance(data, dict) and "plan" in data:
                return data
        except (json.JSONDecodeError, ValueError, TypeError):
            pass
    return None


# ── Rule-based fallback (LLM/파싱 실패 시) ────────────────────────


def _rule_based_planning(state: SellerCopilotState, is_replan: bool) -> Dict:
    """LLM 없이 룰 기반으로 plan + 4 정책 필드를 결정한다."""
    product = state.get("confirmed_product") or {}
    market = state.get("market_context") or {}
    critic_feedback = state.get("critic_feedback") or []
    user_input = state.get("user_product_input") or {}
    goal = state.get("mission_goal", "balanced")

    missing: List[str] = []
    rationale: List[str] = []
    steps = ["identify_product", "analyze_market", "set_pricing", "generate_listing", "critique_listing"]

    # 상품 정보 분석
    if not product.get("model"):
        missing.append("model_name")
        rationale.append("상품 모델명이 확인되지 않음")

    if not product.get("brand") or product.get("brand", "").lower() == "unknown":
        missing.append("brand")
        rationale.append("브랜드 정보 부족")

    sample_count = market.get("sample_count", 0) if market else 0
    if sample_count < 3:
        rationale.append("시장 데이터 부족 — 유사 모델 확장 검색 필요")
        steps.insert(2, "expand_market_search")

    # replan 시 critic 피드백 반영
    if is_replan and critic_feedback:
        trust_issues = [f for f in critic_feedback if f.get("type") == "trust"]
        if trust_issues:
            missing.append("product_condition_details")
            rationale.append("구매자 신뢰 정보 부족 — 상태/구성품 정보 필요")

        seo_issues = [f for f in critic_feedback if f.get("type") in ("title", "seo")]
        if seo_issues:
            rationale.append("검색 최적화 부족 — 제목 키워드 보강 필요")

        steps.append("rewrite_with_critic_feedback")

    focus_map = {
        "fast_sell": "빠른 판매를 위한 공격적 가격·간결한 문구",
        "profit_max": "수익 극대화를 위한 프리미엄 포지셔닝",
        "balanced": "적정 가격·신뢰도 균형",
    }

    # ── 4 정책 필드 추론 (룰 기반) ─────────────────────────────────
    has_user_price = bool(user_input.get("price"))
    info_rich = bool(product.get("model")) and bool(product.get("brand")) and not is_replan
    info_poor = bool(missing) or sample_count < 3

    if is_replan or info_poor:
        plan_mode = "deep"
    elif info_rich and has_user_price:
        plan_mode = "shallow"
    else:
        plan_mode = "balanced"

    if has_user_price and info_rich:
        market_depth = "skip"   # routing의 _skip_allowed() 가드를 통과해야 실제 적용됨
    elif info_rich and not is_replan:
        market_depth = "crawl_only"
    else:
        market_depth = "crawl_plus_rag"

    # critic_policy는 plan_mode와 호환되는 범위 내에서 선택
    if plan_mode == "shallow":
        critic_policy = "minimal" if not is_replan else "normal"
    elif plan_mode == "deep":
        critic_policy = "strict" if is_replan else "normal"
    else:
        critic_policy = "normal"

    clarification_policy = "ask_early" if info_poor else "ask_late"

    return {
        "mission_goal": goal,
        "plan": {
            "steps": steps,
            "focus": focus_map.get(goal, focus_map["balanced"]),
        },
        "rationale": rationale or ["기본 판매 플로우 실행"],
        "missing_information": missing,
        "plan_mode": plan_mode,
        "market_depth": market_depth,
        "critic_policy": critic_policy,
        "clarification_policy": clarification_policy,
    }
