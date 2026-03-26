"""
listing_llm — LLM 호출 어댑터 (OpenAI / Gemini / Solar).

ListingService의 판매글 생성에 필요한 LLM HTTP 호출을 모두 담당.
순수 async 함수로 제공하며, fallback 체인(generate_copy)도 여기서 관리.
"""
from __future__ import annotations

import asyncio
from typing import Any

import logging

import httpx

logger = logging.getLogger(__name__)

from app.core.config import settings
from app.services.listing_prompt import build_copy_prompt, extract_json_object


async def generate_copy_with_openai(
    confirmed_product: dict,
    market_context: dict,
    strategy: dict,
    image_paths: list[str],
    tool_calls_context: str = "",
) -> dict[str, Any]:
    if not settings.openai_api_key:
        raise ValueError("OPENAI_API_KEY is not configured")

    prompt = build_copy_prompt(
        confirmed_product=confirmed_product,
        market_context=market_context,
        strategy=strategy,
        image_paths=image_paths,
        tool_calls_context=tool_calls_context,
    )

    headers = {
        "Authorization": f"Bearer {settings.openai_api_key}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": settings.openai_listing_model,
        "messages": [
            {"role": "system", "content": "You generate structured JSON listing drafts."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.3,
    }

    last_error = None
    for delay in (0, 2, 5):
        if delay > 0:
            await asyncio.sleep(delay)
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers=headers,
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
            text = data["choices"][0]["message"]["content"]
            return extract_json_object(text)
        except httpx.HTTPStatusError as e:
            last_error = e
            if e.response.status_code == 429:
                continue
            raise

    raise last_error if last_error else ValueError("OpenAI request failed")


async def generate_copy_with_gemini(
    confirmed_product: dict,
    market_context: dict,
    strategy: dict,
    image_paths: list[str],
    tool_calls_context: str = "",
) -> dict[str, Any]:
    if not getattr(settings, "gemini_api_key", None):
        raise ValueError("GEMINI_API_KEY is not configured")

    gemini_model = getattr(settings, "gemini_listing_model", None)
    if not gemini_model:
        raise ValueError("GEMINI_LISTING_MODEL is not configured")

    prompt = build_copy_prompt(
        confirmed_product=confirmed_product,
        market_context=market_context,
        strategy=strategy,
        image_paths=image_paths,
        tool_calls_context=tool_calls_context,
    )

    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{gemini_model}:generateContent"
        f"?key={settings.gemini_api_key}"
    )

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.3},
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(url, json=payload)
        response.raise_for_status()
        data = response.json()

    candidates = data.get("candidates", [])
    if not candidates:
        raise ValueError("Gemini returned no candidates")

    parts = candidates[0].get("content", {}).get("parts", [])
    if not parts:
        raise ValueError("Gemini returned no content parts")

    text = "".join(part.get("text", "") for part in parts).strip()
    return extract_json_object(text)


async def generate_copy_with_solar(
    confirmed_product: dict,
    market_context: dict,
    strategy: dict,
    image_paths: list[str],
    tool_calls_context: str = "",
) -> dict[str, Any]:
    if not getattr(settings, "upstage_api_key", None):
        raise ValueError("UPSTAGE_API_KEY is not configured")

    solar_model = getattr(settings, "solar_listing_model", None)
    if not solar_model:
        raise ValueError("SOLAR_LISTING_MODEL is not configured")

    prompt = build_copy_prompt(
        confirmed_product=confirmed_product,
        market_context=market_context,
        strategy=strategy,
        image_paths=image_paths,
        tool_calls_context=tool_calls_context,
    )

    headers = {
        "Authorization": f"Bearer {settings.upstage_api_key}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": solar_model,
        "messages": [
            {"role": "system", "content": "You generate structured JSON listing drafts."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.3,
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            "https://api.upstage.ai/v1/solar/chat/completions",
            headers=headers,
            json=payload,
        )
        response.raise_for_status()
        data = response.json()

    text = data["choices"][0]["message"]["content"]
    return extract_json_object(text)


def build_template_copy(
    confirmed_product: dict,
    market_context: dict,
    strategy: dict,
) -> dict[str, Any]:
    """LLM 전체 실패 시 규칙 기반 폴백 판매글을 생성한다."""
    brand = confirmed_product.get("brand") or ""
    model = confirmed_product.get("model") or "상품"
    category = confirmed_product.get("category") or "중고 상품"

    recommended_price = strategy.get("recommended_price", 0)
    median_price = market_context.get("median_price", 0)
    price_band = market_context.get("price_band", [])

    brand_prefix = f"{brand} " if brand and brand.lower() != "unknown" else ""
    title = f"{brand_prefix}{model} 판매합니다".strip()

    price_line = ""
    if recommended_price > 0:
        price_line = f"희망 가격은 {recommended_price:,}원입니다."
    elif median_price > 0:
        price_line = f"최근 시세 기준 참고 가격은 {median_price:,}원 수준입니다."

    band_line = ""
    if isinstance(price_band, list) and len(price_band) == 2:
        low, high = price_band
        band_line = f"유사 매물 시세는 대략 {low:,}원~{high:,}원 범위로 확인됐습니다."

    description_parts = [
        f"{brand_prefix}{model} 판매합니다.".strip(),
        f"카테고리는 {category}입니다.",
        price_line,
        band_line,
        "상태는 사진 참고 부탁드립니다.",
        "직거래/택배거래 여부는 협의 가능합니다.",
        "관심 있으시면 편하게 문의 주세요.",
    ]

    description = " ".join(part for part in description_parts if part)

    tags = [model]
    if brand and brand.lower() != "unknown":
        tags.append(brand)
    if category and category.lower() != "unknown":
        tags.append(category)

    deduped_tags: list[str] = []
    seen: set[str] = set()
    for tag in tags:
        normalized = str(tag).strip()
        if normalized and normalized not in seen:
            deduped_tags.append(normalized)
            seen.add(normalized)

    return {
        "title": title,
        "description": description,
        "price": recommended_price,
        "tags": deduped_tags[:5],
        "images": [],
        "strategy": strategy.get("goal", "balanced"),
        "product": confirmed_product,
    }


async def generate_copy(
    confirmed_product: dict,
    market_context: dict,
    strategy: dict,
    image_paths: list[str],
    tool_calls_context: str = "",
) -> dict[str, Any]:
    """provider_order_map 기반 fallback dispatch.

    primary provider 실패 시 나머지 provider를 순서대로 시도.
    전부 실패하면 build_template_copy() 규칙 기반 폴백 반환.
    """
    provider_order_map = {
        "openai": ["openai", "gemini", "solar"],
        "gemini": ["gemini", "openai", "solar"],
        "solar": ["solar", "openai", "gemini"],
    }

    primary = getattr(settings, "listing_llm_provider", "openai")
    provider_order = provider_order_map.get(primary, ["openai", "gemini", "solar"])

    for provider in provider_order:
        try:
            if provider == "openai":
                return await generate_copy_with_openai(
                    confirmed_product=confirmed_product,
                    market_context=market_context,
                    strategy=strategy,
                    image_paths=image_paths,
                    tool_calls_context=tool_calls_context,
                )
            if provider == "gemini":
                return await generate_copy_with_gemini(
                    confirmed_product=confirmed_product,
                    market_context=market_context,
                    strategy=strategy,
                    image_paths=image_paths,
                    tool_calls_context=tool_calls_context,
                )
            if provider == "solar":
                return await generate_copy_with_solar(
                    confirmed_product=confirmed_product,
                    market_context=market_context,
                    strategy=strategy,
                    image_paths=image_paths,
                    tool_calls_context=tool_calls_context,
                )
        except Exception as exc:
            logger.warning("LLM provider %s failed: %s", provider, exc)
            continue

    return build_template_copy(
        confirmed_product=confirmed_product,
        market_context=market_context,
        strategy=strategy,
    )
