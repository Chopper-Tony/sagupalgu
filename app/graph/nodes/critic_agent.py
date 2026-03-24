"""
Agent 6 — Listing Critic 에이전트

판매글 품질을 구매자 관점에서 평가하고,
rewrite가 필요하면 구체적 수정 지시를 생성한다.

출력:
  critic_score: 0~100
  critic_feedback: [{type, impact, reason}]
  critic_rewrite_instructions: [str]
  → routing: "pass" | "rewrite" | "recover"
"""
from __future__ import annotations

import json
from typing import Dict

from app.graph.seller_copilot_state import SellerCopilotState
from app.graph.nodes.helpers import _build_react_llm, _log, _record_error, _run_async, _safe_int


CRITIC_PASS_THRESHOLD = 70


def listing_critic_node(state: SellerCopilotState) -> SellerCopilotState:
    """판매글 품질을 LLM으로 비평하고 rewrite 여부를 결정한다."""
    _log(state, "agent6:critic:start")

    listing = state.get("canonical_listing")
    if not listing:
        _record_error(state, "listing_critic", "canonical_listing missing")
        state["critic_score"] = 0
        state["critic_feedback"] = [{"type": "missing", "impact": "high", "reason": "판매글이 없습니다"}]
        state["critic_rewrite_instructions"] = []
        return state

    product = state.get("confirmed_product") or {}
    strategy = state.get("strategy") or {}
    market_context = state.get("market_context") or {}

    # LLM 기반 비평 시도
    critique = _run_llm_critique(state, listing, product, strategy, market_context)

    if critique:
        state["critic_score"] = critique.get("score", 0)
        state["critic_feedback"] = critique.get("issues", [])
        state["critic_rewrite_instructions"] = critique.get("rewrite_instructions", [])
    else:
        # LLM 실패 시 룰 기반 fallback
        critique = _rule_based_critique(listing, product, market_context)
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
        _record_error(state, "listing_critic", f"LLM critique failed: {e}")
        _log(state, f"agent6:critic:llm_failed error={e} → rule fallback")
        return None


def _build_critic_prompt(listing: Dict, product: Dict, strategy: Dict, market_context: Dict) -> str:
    """비평 프롬프트를 조립한다."""
    goal = strategy.get("goal", "fast_sell")
    median_price = market_context.get("median_price", 0)

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

평가 기준:
- 제목: 검색 키워드 포함, 모델명 명확, 클릭 유도
- 설명: 상태 정보, 구성품, 거래 조건 포함 여부
- 가격: 시세 대비 적정성 (시세 중앙값: {median_price}원)
- 신뢰: 구매자가 안심할 수 있는 정보 포함 여부
- 판매 목표: {goal}

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
    except Exception:
        pass
    m = re.search(r"\{.*\}", content, re.DOTALL)
    if m:
        try:
            data = json.loads(m.group(0))
            if isinstance(data, dict) and "score" in data:
                return data
        except Exception:
            pass
    return None


def _rule_based_critique(listing: Dict, product: Dict, market_context: Dict) -> Dict:
    """LLM 없이 룰 기반으로 판매글을 평가한다."""
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

    # 설명 검사
    if len(description) < 50:
        score -= 15
        issues.append({"type": "description", "impact": "high", "reason": "설명이 너무 짧습니다"})
        rewrite_instructions.append("설명에 상태, 구성품, 거래 조건을 포함하세요")

    trust_keywords = ["상태", "구성품", "사용", "배터리", "보증", "직거래", "택배"]
    if not any(kw in description for kw in trust_keywords):
        score -= 10
        issues.append({"type": "trust", "impact": "high", "reason": "구매자 신뢰 정보가 부족합니다"})
        rewrite_instructions.append("설명에 상품 상태와 거래 방법 정보를 추가하세요")

    # 가격 검사
    if price <= 0:
        score -= 20
        issues.append({"type": "price", "impact": "high", "reason": "가격이 0원입니다"})

    if median_price > 0 and price > median_price * 1.3:
        score -= 10
        issues.append({"type": "price", "impact": "medium", "reason": "시세 대비 30% 이상 높습니다"})

    return {
        "score": max(0, score),
        "issues": issues,
        "rewrite_instructions": rewrite_instructions,
    }
