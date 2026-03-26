"""
Agent 0 — Mission Planner 에이전트

세션 상태를 해석하고 실행 계획을 생성한다.
Critic이 replan을 요청하면 계획을 수정한다.

출력:
  mission_goal: fast_sell | balanced | profit_max
  plan: {steps: [...], focus: str}
  decision_rationale: [str]
  missing_information: [str]
"""
from __future__ import annotations

import json
from typing import Dict, List

from app.graph.seller_copilot_state import SellerCopilotState
from app.graph.nodes.helpers import _build_react_llm, _log, _record_error, _record_node_timing, _run_async, _start_timer


def mission_planner_node(state: SellerCopilotState) -> SellerCopilotState:
    """세션 상태를 분석하고 실행 계획을 생성/수정한다."""
    _timer = _start_timer()
    _log(state, "agent0:planner:start")

    is_replan = state.get("plan_revision_count", 0) > 0
    if is_replan:
        _log(state, f"agent0:planner:replan revision={state['plan_revision_count']}")

    # LLM 기반 계획 시도
    plan_result = _run_llm_planning(state, is_replan)

    if plan_result:
        state["plan"] = plan_result.get("plan", {})
        state["mission_goal"] = plan_result.get("mission_goal", state.get("mission_goal", "balanced"))
        state["decision_rationale"] = state.get("decision_rationale", []) + plan_result.get("rationale", [])
        state["missing_information"] = plan_result.get("missing_information", [])
    else:
        # LLM 실패 시 룰 기반 fallback
        plan_result = _rule_based_planning(state, is_replan)
        state["plan"] = plan_result["plan"]
        state["mission_goal"] = plan_result["mission_goal"]
        state["decision_rationale"] = state.get("decision_rationale", []) + plan_result["rationale"]
        state["missing_information"] = plan_result["missing_information"]

    _log(state, f"agent0:planner:done goal={state['mission_goal']} steps={len(state['plan'].get('steps', []))}")
    _record_node_timing(state, "mission_planner", _timer)
    return state


def _run_llm_planning(state: SellerCopilotState, is_replan: bool) -> Dict | None:
    """LLM을 사용해 실행 계획을 생성한다."""
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
        _record_error(state, "mission_planner", f"LLM planning failed: {e}")
        _log(state, f"agent0:planner:llm_failed error={e}")
        return None


def _build_planner_prompt(state: SellerCopilotState, is_replan: bool) -> str:
    """플래너 프롬프트를 조립한다."""
    product = state.get("confirmed_product") or {}
    market = state.get("market_context") or {}
    critic_feedback = state.get("critic_feedback") or []
    current_goal = state.get("mission_goal", "balanced")

    context_parts = [
        f"상품: {product.get('brand', '')} {product.get('model', '')} ({product.get('category', '')})",
        f"현재 목표: {current_goal}",
    ]
    if market:
        context_parts.append(f"시장 데이터: 중앙값 {market.get('median_price', 0)}원, 샘플 {market.get('sample_count', 0)}개")

    replan_context = ""
    if is_replan and critic_feedback:
        issues = [f"- [{f.get('type', '?')}] {f.get('reason', '')}" for f in critic_feedback[:3]]
        replan_context = f"\n\n이전 판매글 비평 결과:\n" + "\n".join(issues) + "\n위 문제를 해결하도록 계획을 수정하세요."

    return f"""당신은 중고거래 판매 전략 플래너입니다.
아래 상황을 분석하고 실행 계획을 JSON으로 작성하세요.

반드시 아래 형식으로만 응답:
{{
  "mission_goal": "fast_sell|balanced|profit_max",
  "plan": {{
    "steps": ["step1", "step2", ...],
    "focus": "핵심 전략 한 줄"
  }},
  "rationale": ["판단 근거1", "판단 근거2"],
  "missing_information": ["부족한 정보1", "부족한 정보2"]
}}

현재 상황:
{chr(10).join(context_parts)}
{replan_context}"""


def _parse_plan_response(content: str) -> Dict | None:
    """LLM 응답에서 plan JSON을 추출한다."""
    import re
    content = content.strip()
    if content.startswith("```"):
        content = re.sub(r"^```(?:json)?", "", content).strip()
        content = re.sub(r"```$", "", content).strip()
    try:
        data = json.loads(content)
        if isinstance(data, dict) and "plan" in data:
            return data
    except Exception:
        pass
    m = re.search(r"\{.*\}", content, re.DOTALL)
    if m:
        try:
            data = json.loads(m.group(0))
            if isinstance(data, dict) and "plan" in data:
                return data
        except Exception:
            pass
    return None


def _rule_based_planning(state: SellerCopilotState, is_replan: bool) -> Dict:
    """LLM 없이 룰 기반으로 실행 계획을 생성한다."""
    product = state.get("confirmed_product") or {}
    market = state.get("market_context") or {}
    critic_feedback = state.get("critic_feedback") or []
    goal = state.get("mission_goal", "balanced")

    missing = []
    rationale = []
    steps = ["identify_product", "analyze_market", "set_pricing", "generate_listing", "critique_listing"]

    # 상품 정보 분석
    if not product.get("model"):
        missing.append("model_name")
        rationale.append("상품 모델명이 확인되지 않음")

    if not product.get("brand") or product.get("brand", "").lower() == "unknown":
        missing.append("brand")
        rationale.append("브랜드 정보 부족")

    # 시장 데이터 분석
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

    return {
        "mission_goal": goal,
        "plan": {
            "steps": steps,
            "focus": focus_map.get(goal, focus_map["balanced"]),
        },
        "rationale": rationale or ["기본 판매 플로우 실행"],
        "missing_information": missing,
    }
