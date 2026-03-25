"""
판매글 생성 프롬프트 빌더, 응답 파서, 가격 전략.

ListingService에서 순수 함수를 분리해 단독 테스트·재사용이 가능하게 한다.
"""
from __future__ import annotations

import json
import re
from typing import Any


def build_copy_prompt(
    confirmed_product: dict,
    market_context: dict,
    strategy: dict,
    image_paths: list[str],
    tool_calls_context: str = "",
) -> str:
    """판매글 생성 LLM 프롬프트 조립."""
    brand = confirmed_product.get("brand", "Unknown")
    model = confirmed_product.get("model", "상품")
    category = confirmed_product.get("category", "unknown")
    confidence = confirmed_product.get("confidence", 0.0)

    median_price = market_context.get("median_price", 0)
    price_band = market_context.get("price_band", [])
    sample_count = market_context.get("sample_count", 0)

    recommended_price = strategy.get("recommended_price", 0)
    goal = strategy.get("goal", "fast_sell")
    negotiation_policy = strategy.get("negotiation_policy", "")

    prompt = f"""
You are an expert seller copilot for secondhand marketplace listings.

Return ONLY valid JSON:

{{
  "title": "string",
  "description": "string",
  "tags": ["string", "string", "string"]
}}

Rules:
- Write in Korean.
- Keep the title natural and marketplace-friendly.
- Keep the description practical, concise, and trustworthy.
- Do not invent specs not explicitly provided.
- Reflect uncertainty conservatively.
- Tags must be short and useful, maximum 5.
- Do not wrap JSON in markdown fences.

Product:
- brand: {brand}
- model: {model}
- category: {category}
- confidence: {confidence}

Market:
- median_price: {median_price}
- price_band: {price_band}
- sample_count: {sample_count}

Strategy:
- goal: {goal}
- recommended_price: {recommended_price}
- negotiation_policy: {negotiation_policy}

Image paths:
- {image_paths}
""".strip()

    if tool_calls_context:
        prompt += f"\n\nAgent tool call history (for context):\n{tool_calls_context}"

    return prompt


def extract_json_object(text: str) -> dict[str, Any]:
    """LLM 응답 텍스트에서 JSON 객체 추출. 마크다운 펜스 자동 제거."""
    text = text.strip()

    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text).strip()
        text = re.sub(r"```$", "", text).strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            raise ValueError("LLM did not return valid JSON")
        return json.loads(match.group(0))


# ── Context 빌더 ─────────────────────────────────────────────────


def build_tool_calls_context(tool_calls: list[dict]) -> str:
    """에이전트 tool_calls 리스트를 LLM 컨텍스트 문자열로 변환."""
    if not tool_calls:
        return ""
    lines = []
    for tc in tool_calls:
        tool_name = tc.get("tool_name", "unknown")
        success = tc.get("success", False)
        lines.append(f"- {tool_name}: {'success' if success else 'failed'}")
    return "\n".join(lines)


def build_rewrite_context(canonical_listing: dict, instruction: str) -> str:
    """재작성 요청을 LLM 컨텍스트 문자열로 변환."""
    return (
        f"[재작성 요청]\n"
        f"기존 제목: {canonical_listing.get('title', '')}\n"
        f"기존 설명: {(canonical_listing.get('description') or '')[:200]}\n"
        f"수정 지시: {instruction}\n"
        f"위 지시사항을 반영해 판매글을 개선하라."
    )


# ── 가격 전략 ────────────────────────────────────────────────────


def build_pricing_strategy(
    median_price: int | float,
    goal: str = "balanced",
) -> dict[str, Any]:
    """시세 기반 가격 전략을 생성한다. goal에 따라 배수·정책이 달라진다."""
    from app.domain.goal_strategy import get_negotiation_policy, get_pricing_multiplier

    multiplier = get_pricing_multiplier(goal, sample_count=3)
    if median_price <= 0:
        recommended_price = 0
    else:
        recommended_price = int(median_price * multiplier)

    return {
        "goal": goal,
        "recommended_price": recommended_price,
        "negotiation_policy": get_negotiation_policy(goal),
    }
