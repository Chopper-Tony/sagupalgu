"""
판매글 생성 프롬프트 빌더 및 LLM 응답 파서.

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
