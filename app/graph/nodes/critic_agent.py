"""
Agent 6 — Listing Critic / Routing Agent

분류 (Target Architecture, 4+2+5):
  listing_critic_node → Routing Agent
                        LLM이 평가 + repair_action·failure_mode·rewrite_plan을 직접 결정.
                        routing.py는 단순 dispatch (state["repair_action"] → 노드 이름).

출력:
  critic_score: 0~100 (관측용 — UI/workflow_meta 호환성. 라우팅에는 안 쓴다)
  critic_feedback: [{type, impact, reason}]
  critic_rewrite_instructions: [str]   (관측용)
  repair_action: "pass" | "rewrite_title" | "rewrite_description" | "rewrite_full" | "reprice" | "clarify" | "replan"
  failure_mode:  "title_weak" | "price_off" | "info_missing" | "untrusted_seller" |
                 "critic_parse_error" | "replan_limit_reached" | None
  rewrite_plan:  {target: "title|description|full", instruction: str}

엄격도:
  state.critic_policy ∈ {"minimal", "normal", "strict"} 로 프롬프트가 동적으로 바뀐다.
  기본은 "normal" (PR1 baseline) — 현재 동작과 사실상 동등.

파싱 실패 시 (failure_mode = "critic_parse_error"):
  팀 기준 — "조용한 통과"가 아니라 *"critic 판단 실패 시 validation_rules를 최종 안전망으로
  사용한다"* 는 의미. repair_action="pass"로 두고 routing.py가 validation_rules로 보낸다.
  쓰는 사람이 추적할 수 있게 failure_mode와 debug_logs에 사유를 남긴다.
"""
from __future__ import annotations

import json
import re
from typing import Dict, List, Optional, Tuple

import logging

from app.domain.critic_policy import CRITIC_PASS_THRESHOLD
from app.graph.seller_copilot_state import SellerCopilotState
from app.graph.nodes.helpers import (
    _build_react_llm,
    _log,
    _record_error,
    _record_node_timing,
    _run_async,
    _safe_int,
    _start_timer,
)


_VALID_REPAIR_ACTIONS = {
    "pass",
    "rewrite_title",
    "rewrite_description",
    "rewrite_full",
    "reprice",
    "clarify",
    "replan",
}

_REWRITE_TARGETS = {"title", "description", "full"}


def listing_critic_node(state: SellerCopilotState) -> SellerCopilotState:
    """판매글 품질을 평가하고 repair_action을 결정한다 (Routing Agent)."""
    _timer = _start_timer()
    _log(state, "agent6:critic:start")

    listing = state.get("canonical_listing")
    if not listing:
        _record_error(state, "listing_critic", "canonical_listing missing")
        state["critic_score"] = 0
        state["critic_feedback"] = [{"type": "missing", "impact": "high", "reason": "판매글이 없습니다"}]
        state["critic_rewrite_instructions"] = []
        state["repair_action"] = "pass"
        state["failure_mode"] = "missing_listing"
        state["rewrite_plan"] = {}
        state.setdefault("debug_logs", []).append("critic:no_canonical_listing → pass(safety net)")
        _record_node_timing(state, "listing_critic", _timer)
        return state

    product = state.get("confirmed_product") or {}
    strategy = state.get("strategy") or {}
    market_context = state.get("market_context") or {}
    goal = state.get("mission_goal", "balanced")
    critic_policy = state.get("critic_policy", "normal")

    # LLM 기반 평가 + 라우팅 결정
    critique = _run_llm_critique(state, listing, product, strategy, market_context, critic_policy)

    if critique is None:
        # ── critic_parse_error fallback ──────────────────────────
        # "조용한 통과" 아님. validation_rules를 deterministic safety net으로 사용한다는 의미.
        _log(state, "agent6:critic:parse_failed → safety_net pass + failure_mode")
        rule = _rule_based_critique(listing, product, market_context, goal=goal)
        state["critic_score"] = rule["score"]
        state["critic_feedback"] = rule["issues"]
        state["critic_rewrite_instructions"] = rule["rewrite_instructions"]
        state["repair_action"] = "pass"
        state["failure_mode"] = "critic_parse_error"
        state["rewrite_plan"] = {}
        state.setdefault("debug_logs", []).append(
            "critic:critic_parse_error → repair_action=pass (safety net via validation_rules)"
        )
        _record_node_timing(state, "listing_critic", _timer)
        return state

    score = int(critique.get("score", 0))
    issues = list(critique.get("issues") or [])
    rewrite_instructions = list(critique.get("rewrite_instructions") or [])
    repair_action, failure_mode, rewrite_plan = _decide_routing(
        critique, score, state, listing, product, market_context,
    )

    state["critic_score"] = score
    state["critic_feedback"] = issues
    state["critic_rewrite_instructions"] = rewrite_instructions
    state["repair_action"] = repair_action
    state["failure_mode"] = failure_mode
    state["rewrite_plan"] = rewrite_plan

    # rewrite로 보낼 때 copywriting이 참조할 instruction을 채운다 (단일 툴 노드 강등 후에도 호환)
    if repair_action.startswith("rewrite") and rewrite_instructions:
        state["rewrite_instruction"] = " / ".join(rewrite_instructions)

    # critic_retry_count 증가 (rewrite 한도 추적용 — copywriting → critic 루프)
    if repair_action.startswith("rewrite"):
        state["critic_retry_count"] = int(state.get("critic_retry_count") or 0) + 1
    elif repair_action == "replan":
        state["plan_revision_count"] = int(state.get("plan_revision_count") or 0) + 1

    _log(
        state,
        f"agent6:critic:done score={score} action={repair_action} "
        f"failure_mode={failure_mode} retry={state.get('critic_retry_count', 0)}",
    )
    _record_node_timing(state, "listing_critic", _timer)
    return state


# ── 라우팅 결정 ────────────────────────────────────────────────────────


def _decide_routing(
    critique: Dict,
    score: int,
    state: SellerCopilotState,
    listing: Dict,
    product: Dict,
    market_context: Dict,
) -> Tuple[str, Optional[str], Dict]:
    """LLM critique JSON에서 repair_action / failure_mode / rewrite_plan 추출.

    LLM이 명시적으로 repair_action을 반환했으면 그걸 신뢰하고, 못 반환했으면
    issues + score로 결정론적으로 추론한다 (legacy 호환).
    """
    raw_action = (critique.get("repair_action") or "").strip().lower()
    failure_mode = critique.get("failure_mode")
    rewrite_plan_raw = critique.get("rewrite_plan") or {}

    # ── 1) LLM이 명시적으로 반환한 경우 ─────────────────────────
    if raw_action in _VALID_REPAIR_ACTIONS:
        # rewrite_plan 정규화
        rewrite_plan = _normalize_rewrite_plan(rewrite_plan_raw, raw_action, critique)

        # critic_retry_count 한도 도달 → 강제 pass
        retry_count = int(state.get("critic_retry_count") or 0)
        max_retries = int(state.get("max_critic_retries") or 2)
        if raw_action.startswith("rewrite") and retry_count >= max_retries:
            return "pass", "max_critic_retries_reached", {}

        return raw_action, failure_mode, rewrite_plan

    # ── 2) LLM이 미반환 — issues + score로 추론 (legacy 경로) ──
    issues = critique.get("issues") or []
    issue_types = {(i.get("type") or "").lower() for i in issues if isinstance(i, dict)}

    # 통과 가이드라인
    if score >= CRITIC_PASS_THRESHOLD and not any(
        i.get("impact") == "high" for i in issues if isinstance(i, dict)
    ):
        return "pass", None, {}

    # rewrite 한도 도달 → 강제 pass
    retry_count = int(state.get("critic_retry_count") or 0)
    max_retries = int(state.get("max_critic_retries") or 2)
    if retry_count >= max_retries:
        return "pass", "max_critic_retries_reached", {}

    # 가격 문제 단독 → reprice
    if "price" in issue_types and not (issue_types - {"price", "seo"}):
        price_issue = next((i for i in issues if i.get("type") == "price"), {})
        return "reprice", "price_off", {"target": "price", "instruction": price_issue.get("reason", "")}

    # 정보 부족 → clarify
    if any(i.get("type") == "trust" and i.get("impact") == "high" for i in issues if isinstance(i, dict)):
        rationale = next(
            (i.get("reason") for i in issues if i.get("type") == "trust"), "정보 부족"
        )
        return "clarify", "info_missing", {"instruction": rationale}

    # 제목만 문제 → rewrite_title
    if issue_types & {"title", "seo"} and not (issue_types & {"description", "trust"}):
        return "rewrite_title", "title_weak", {
            "target": "title",
            "instruction": " / ".join(critique.get("rewrite_instructions") or []) or "제목 강화",
        }

    # 설명만 문제 → rewrite_description
    if "description" in issue_types and not (issue_types & {"title", "seo"}):
        return "rewrite_description", "description_weak", {
            "target": "description",
            "instruction": " / ".join(critique.get("rewrite_instructions") or []) or "설명 강화",
        }

    # 기본: rewrite_full
    return "rewrite_full", "general_quality", {
        "target": "full",
        "instruction": " / ".join(critique.get("rewrite_instructions") or []) or "전체 재작성",
    }


def _normalize_rewrite_plan(raw: Dict, action: str, critique: Dict) -> Dict:
    """rewrite_plan을 안전하게 정규화."""
    if action == "pass" or action == "replan":
        return {}
    if action == "reprice":
        return {"target": "price", "instruction": str(raw.get("instruction") or "")}
    if action == "clarify":
        return {"instruction": str(raw.get("instruction") or "")}

    # rewrite_*
    target_from_action = action.replace("rewrite_", "")  # "title" / "description" / "full"
    target = str(raw.get("target") or target_from_action).lower()
    if target not in _REWRITE_TARGETS:
        target = target_from_action if target_from_action in _REWRITE_TARGETS else "full"
    instruction = str(raw.get("instruction") or "") or " / ".join(
        critique.get("rewrite_instructions") or []
    ) or f"{target} 강화"
    return {"target": target, "instruction": instruction}


# ── LLM 호출 ──────────────────────────────────────────────────────────


def _run_llm_critique(
    state: SellerCopilotState,
    listing: Dict,
    product: Dict,
    strategy: Dict,
    market_context: Dict,
    critic_policy: str,
) -> Optional[Dict]:
    """LLM을 사용해 판매글을 비평하고 repair_action을 결정."""
    try:
        llm = _build_react_llm()
        if llm is None:
            return None

        prompt = _build_critic_prompt(listing, product, strategy, market_context, critic_policy)

        from langchain_core.messages import HumanMessage
        result = _run_async(lambda: llm.ainvoke([HumanMessage(content=prompt)]))

        content = result.content if hasattr(result, "content") else str(result)
        return _parse_critique_response(content)

    except Exception as e:
        logging.getLogger(__name__).error("agent6 LLM critique failed", exc_info=True)
        _record_error(state, "listing_critic", f"LLM critique failed: {e}")
        _log(state, f"agent6:critic:llm_failed error={e}")
        return None


def _build_critic_prompt(
    listing: Dict, product: Dict, strategy: Dict, market_context: Dict, critic_policy: str,
) -> str:
    """비평 프롬프트를 조립한다. critic_policy로 엄격도 조절."""
    from app.domain.goal_strategy import get_copywriting_tone

    goal = strategy.get("goal", "balanced")
    median_price = market_context.get("median_price", 0)
    tone_desc = get_copywriting_tone(goal)

    goal_guidance = {
        "fast_sell": "빠른 판매가 목표입니다. 간결함과 긴급감을 중시하되, 너무 짧으면 감점하세요.",
        "balanced": "적정 가격과 신뢰도 균형이 목표입니다. 상태·구성품 정보 충실도를 중시하세요.",
        "profit_max": "수익 극대화가 목표입니다. 프리미엄 느낌과 상세 스펙 부각을 중시하세요.",
    }.get(goal, "적정 가격과 신뢰도 균형이 목표입니다.")

    # critic_policy 별 엄격도 가이드 (PR3 planner가 동적으로 조절)
    policy_guidance = {
        "minimal":
            f"매우 관대한 평가. 명백한 결함만 지적. score >= {CRITIC_PASS_THRESHOLD - 10} 이면 pass.",
        "normal":
            f"균형 잡힌 평가. score >= {CRITIC_PASS_THRESHOLD} 이면 pass. (이 PR의 baseline)",
        "strict":
            f"엄격한 평가. 사소한 결함도 지적. score >= {CRITIC_PASS_THRESHOLD + 10} 이어야 pass.",
    }.get(critic_policy, f"score >= {CRITIC_PASS_THRESHOLD} 이면 pass.")

    return f"""당신은 중고거래 판매글 품질 평가 + 라우팅 결정 에이전트입니다.
판매글을 구매자 관점에서 평가하고, 다음 액션을 결정하세요.

반드시 아래 JSON 형식으로만 응답하세요 (다른 텍스트 금지):
{{
  "score": 0~100,
  "issues": [
    {{"type": "title|description|price|trust|seo", "impact": "high|medium|low", "reason": "구체적 이유"}}
  ],
  "rewrite_instructions": ["수정 지시1", "수정 지시2"],
  "repair_action": "pass|rewrite_title|rewrite_description|rewrite_full|reprice|clarify|replan",
  "failure_mode": "title_weak|description_weak|price_off|info_missing|untrusted_seller|null",
  "rewrite_plan": {{"target": "title|description|full|price", "instruction": "한 줄 지시"}}
}}

repair_action 결정 가이드:
  - pass:                품질 충분 → validation으로 진행
  - rewrite_title:       제목만 문제 → 제목만 다시 쓰기
  - rewrite_description: 설명만 문제 → 설명만 다시 쓰기
  - rewrite_full:        전반적 문제 → 전체 다시 쓰기
  - reprice:             가격만 시세와 안 맞음 → 가격만 재조정 (가격 외 변경 금지)
  - clarify:             정보 자체가 부족 → 사용자에게 추가 질문
  - replan:              근본적 전략 오류 → planner가 처음부터 다시

평가 정책 ({critic_policy}):
  {policy_guidance}

판매 목표: {goal}
{goal_guidance}
기대 톤: {tone_desc}

평가 기준:
  - 제목: 검색 키워드, 모델명 명확, 클릭 유도
  - 설명: 상태·구성품·거래 조건 포함 여부
  - 가격: 시세 대비 적정성 (시세 중앙값 {median_price}원)
  - 신뢰: 구매자 안심 정보 충실도

판매글:
- 제목: {listing.get('title', '')}
- 설명: {listing.get('description', '')}
- 가격: {listing.get('price', 0)}원
- 태그: {listing.get('tags', [])}

상품 정보:
- 브랜드: {product.get('brand', '')}
- 모델: {product.get('model', '')}
- 카테고리: {product.get('category', '')}"""


def _parse_critique_response(content: str) -> Optional[Dict]:
    """LLM 응답에서 critique JSON을 추출. score 필드만 있으면 valid로 간주 (legacy 호환)."""
    content = content.strip()
    if content.startswith("```"):
        content = re.sub(r"^```(?:json)?", "", content).strip()
        content = re.sub(r"```$", "", content).strip()
    try:
        data = json.loads(content)
        if isinstance(data, dict) and "score" in data:
            return data
    except (json.JSONDecodeError, ValueError, TypeError):
        pass
    m = re.search(r"\{.*\}", content, re.DOTALL)
    if m:
        try:
            data = json.loads(m.group(0))
            if isinstance(data, dict) and "score" in data:
                return data
        except (json.JSONDecodeError, ValueError, TypeError):
            pass
    return None


def _rule_based_critique(
    listing: Dict, product: Dict, market_context: Dict, goal: str = "balanced",
) -> Dict:
    """LLM 없이 룰 기반으로 판매글을 평가한다. critic_parse_error fallback에서만 호출."""
    from app.domain.goal_strategy import get_critic_criteria

    criteria = get_critic_criteria(goal)
    price_threshold = criteria["price_threshold"]
    min_desc_len = criteria["min_desc_len"]
    trust_penalty = criteria["trust_penalty"]

    score = 100
    issues: List[Dict] = []
    rewrite_instructions: List[str] = []

    title = listing.get("title", "")
    description = listing.get("description", "")
    price = _safe_int(listing.get("price"), 0)
    model = product.get("model", "")
    median_price = _safe_int(market_context.get("median_price"), 0)

    if len(title) < 10:
        score -= 15
        issues.append({"type": "title", "impact": "high", "reason": "제목이 너무 짧습니다"})
        rewrite_instructions.append("제목에 브랜드와 모델명, 핵심 특징을 포함하세요")

    if model and model not in title:
        score -= 10
        issues.append({"type": "seo", "impact": "medium", "reason": "제목에 모델명이 없습니다"})
        rewrite_instructions.append(f"제목에 '{model}'을 포함하세요")

    if len(description) < min_desc_len:
        score -= 15
        issues.append({"type": "description", "impact": "high", "reason": f"설명이 너무 짧습니다 (최소 {min_desc_len}자)"})
        rewrite_instructions.append("설명에 상태, 구성품, 거래 조건을 포함하세요")

    trust_keywords = ["상태", "구성품", "사용", "배터리", "보증", "직거래", "택배"]
    if not any(kw in description for kw in trust_keywords):
        score -= trust_penalty
        issues.append({"type": "trust", "impact": "high", "reason": "구매자 신뢰 정보가 부족합니다"})
        rewrite_instructions.append("설명에 상품 상태와 거래 방법 정보를 추가하세요")

    if price <= 0:
        score -= 20
        issues.append({"type": "price", "impact": "high", "reason": "가격이 0원입니다"})

    if median_price > 0 and price > median_price * price_threshold:
        over_pct = int((price_threshold - 1) * 100)
        score -= 10
        issues.append({"type": "price", "impact": "medium", "reason": f"시세 대비 {over_pct}% 이상 높습니다"})

    return {
        "score": max(0, score),
        "issues": issues,
        "rewrite_instructions": rewrite_instructions,
    }
