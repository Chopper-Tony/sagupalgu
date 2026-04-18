"""
Agent 6 — Listing Critic (PR2에서 Routing Agent로 승격 예정)

분류 (Target Architecture, 4+2+5):
  listing_critic_node → Routing Agent (PR2 승격 후)
                        현재는 score만 산출하고 routing.py 외부 if문이 분기 결정.
                        PR2에서 LLM이 repair_action·failure_mode·rewrite_plan 을 직접 결정,
                        routing.py는 단순 dispatch로 축소.

출력 (PR1 시점):
  critic_score: 0~100
  critic_feedback: [{type, impact, reason}]
  critic_rewrite_instructions: [str]
  → routing.py 외부 if문이 score 임계값으로 분기 ("pass" | "rewrite" | "replan")

출력 (PR2 이후 예정):
  critic_score: 관측용으로만 유지 (UI·workflow_meta 호환성)
  repair_action: "pass" | "rewrite_title" | "rewrite_description" | "rewrite_full" | "reprice" | "clarify" | "replan"
  failure_mode: "title_weak" | "price_off" | "info_missing" | "critic_parse_error" | ...
  rewrite_plan: {target, instruction}
  → routing.py 단순 dispatch (state["repair_action"]만 본다)
"""
from __future__ import annotations

import json
from typing import Dict

import logging

from app.graph.seller_copilot_state import SellerCopilotState
from app.graph.nodes.helpers import _build_react_llm, _log, _record_error, _record_node_timing, _run_async, _safe_int, _start_timer


CRITIC_PASS_THRESHOLD = 70


def listing_critic_node(state: SellerCopilotState) -> SellerCopilotState:
    """판매글 품질을 LLM으로 비평하고 rewrite 여부를 결정한다."""
    _timer = _start_timer()
    _log(state, "agent6:critic:start")

    listing = state.get("canonical_listing")
    if not listing:
        _record_error(state, "listing_critic", "canonical_listing missing")
        state["critic_score"] = 0
        state["critic_feedback"] = [{"type": "missing", "impact": "high", "reason": "판매글이 없습니다"}]
        state["critic_rewrite_instructions"] = []
        _record_node_timing(state, "listing_critic", _timer)
        return state

    product = state.get("confirmed_product") or {}
    strategy = state.get("strategy") or {}
    market_context = state.get("market_context") or {}

    goal = state.get("mission_goal", "balanced")

    # LLM 기반 비평 시도
    critique = _run_llm_critique(state, listing, product, strategy, market_context)

    if critique:
        state["critic_score"] = critique.get("score", 0)
        state["critic_feedback"] = critique.get("issues", [])
        state["critic_rewrite_instructions"] = critique.get("rewrite_instructions", [])
    else:
        # LLM 실패 시 룰 기반 fallback
        critique = _rule_based_critique(listing, product, market_context, goal=goal)
        state["critic_score"] = critique["score"]
        state["critic_feedback"] = critique["issues"]
        state["critic_rewrite_instructions"] = critique["rewrite_instructions"]

    score = state["critic_score"]
    retry_count = state.get("critic_retry_count", 0)
    max_retries = state.get("max_critic_retries", 2)

    if score >= CRITIC_PASS_THRESHOLD:
        _log(state, f"agent6:critic:pass score={score}")
    elif retry_count < max_retries:
        state["critic_retry_count"] = retry_count + 1
        # rewrite_instruction에 critic 지시를 넣어 copywriting이 이를 반영
        instructions = state["critic_rewrite_instructions"]
        if instructions:
            state["rewrite_instruction"] = " / ".join(instructions)
        _log(state, f"agent6:critic:rewrite score={score} retry={retry_count + 1}/{max_retries}")
    else:
        _log(state, f"agent6:critic:accept_despite_low_score score={score} max_retries_reached")

    _log(state, "agent6:critic:done")
    _record_node_timing(state, "listing_critic", _timer)
    return state


def _run_llm_critique(
    state: SellerCopilotState,
    listing: Dict,
    product: Dict,
    strategy: Dict,
    market_context: Dict,
) -> Dict | None:
    """LLM을 사용해 판매글을 비평한다."""
    try:
        llm = _build_react_llm()
        if llm is None:
            return None

        prompt = _build_critic_prompt(listing, product, strategy, market_context)

        from langchain_core.messages import HumanMessage
        result = _run_async(lambda: llm.ainvoke([HumanMessage(content=prompt)]))

        content = result.content if hasattr(result, "content") else str(result)
        return _parse_critique_response(content)

    except Exception as e:
        logging.getLogger(__name__).error("agent6 LLM critique failed", exc_info=True)
        _record_error(state, "listing_critic", f"LLM critique failed: {e}")
        _log(state, f"agent6:critic:llm_failed error={e} → rule fallback")
        return None


def _build_critic_prompt(listing: Dict, product: Dict, strategy: Dict, market_context: Dict) -> str:
    """비평 프롬프트를 조립한다."""
    from app.domain.goal_strategy import get_copywriting_tone

    goal = strategy.get("goal", "balanced")
    median_price = market_context.get("median_price", 0)
    tone_desc = get_copywriting_tone(goal)

    goal_guidance = {
        "fast_sell": "빠른 판매가 목표입니다. 간결함과 긴급감을 중시하되, 너무 짧으면 감점하세요.",
        "balanced": "적정 가격과 신뢰도 균형이 목표입니다. 상태·구성품 정보 충실도를 중시하세요.",
        "profit_max": "수익 극대화가 목표입니다. 프리미엄 느낌과 상세 스펙 부각을 중시하세요.",
    }.get(goal, "적정 가격과 신뢰도 균형이 목표입니다.")

    return f"""당신은 중고거래 판매글 품질 평가 전문가입니다.
아래 판매글을 구매자 관점에서 냉정하게 평가하세요.

반드시 아래 JSON 형식으로만 응답하세요:
{{
  "score": 0~100,
  "issues": [
    {{"type": "title|description|price|trust|seo", "impact": "high|medium|low", "reason": "구체적 이유"}}
  ],
  "rewrite_instructions": ["구체적 수정 지시1", "구체적 수정 지시2"]
}}

판매 목표: {goal}
{goal_guidance}
기대 톤: {tone_desc}

평가 기준:
- 제목: 검색 키워드 포함, 모델명 명확, 클릭 유도
- 설명: 상태 정보, 구성품, 거래 조건 포함 여부
- 가격: 시세 대비 적정성 (시세 중앙값: {median_price}원)
- 신뢰: 구매자가 안심할 수 있는 정보 포함 여부

판매글:
- 제목: {listing.get('title', '')}
- 설명: {listing.get('description', '')}
- 가격: {listing.get('price', 0)}원
- 태그: {listing.get('tags', [])}

상품 정보:
- 브랜드: {product.get('brand', '')}
- 모델: {product.get('model', '')}
- 카테고리: {product.get('category', '')}"""


def _parse_critique_response(content: str) -> Dict | None:
    """LLM 응답에서 critique JSON을 추출한다."""
    import re
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
    """LLM 없이 룰 기반으로 판매글을 평가한다. goal에 따라 기준이 달라진다."""
    from app.domain.goal_strategy import get_critic_criteria

    criteria = get_critic_criteria(goal)
    price_threshold = criteria["price_threshold"]
    min_desc_len = criteria["min_desc_len"]
    trust_penalty = criteria["trust_penalty"]

    score = 100
    issues = []
    rewrite_instructions = []

    title = listing.get("title", "")
    description = listing.get("description", "")
    price = _safe_int(listing.get("price"), 0)
    model = product.get("model", "")
    median_price = _safe_int(market_context.get("median_price"), 0)

    # 제목 검사
    if len(title) < 10:
        score -= 15
        issues.append({"type": "title", "impact": "high", "reason": "제목이 너무 짧습니다"})
        rewrite_instructions.append("제목에 브랜드와 모델명, 핵심 특징을 포함하세요")

    if model and model not in title:
        score -= 10
        issues.append({"type": "seo", "impact": "medium", "reason": "제목에 모델명이 없습니다"})
        rewrite_instructions.append(f"제목에 '{model}'을 포함하세요")

    # 설명 검사 (goal별 최소 길이)
    if len(description) < min_desc_len:
        score -= 15
        issues.append({"type": "description", "impact": "high", "reason": f"설명이 너무 짧습니다 (최소 {min_desc_len}자)"})
        rewrite_instructions.append("설명에 상태, 구성품, 거래 조건을 포함하세요")

    trust_keywords = ["상태", "구성품", "사용", "배터리", "보증", "직거래", "택배"]
    if not any(kw in description for kw in trust_keywords):
        score -= trust_penalty
        issues.append({"type": "trust", "impact": "high", "reason": "구매자 신뢰 정보가 부족합니다"})
        rewrite_instructions.append("설명에 상품 상태와 거래 방법 정보를 추가하세요")

    # 가격 검사 (goal별 임계값)
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
