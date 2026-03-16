import asyncio
import json
import re
from typing import Any

import httpx

from app.core.config import settings
from app.services.market.market_service import MarketService


class ListingService:
    def __init__(self):
        self.market_service = MarketService()

    async def build_market_context(self, confirmed_product: dict) -> dict:
        return await self.market_service.analyze_market(confirmed_product)

    async def build_pricing_strategy(
        self,
        confirmed_product: dict,
        market_context: dict,
    ) -> dict:
        median_price = market_context.get("median_price") or 0

        if median_price <= 0:
            recommended_price = 0
        else:
            recommended_price = int(median_price * 0.97)

        return {
            "goal": "fast_sell",
            "recommended_price": recommended_price,
            "negotiation_policy": "small negotiation allowed",
        }

    def _build_copy_prompt(
        self,
        confirmed_product: dict,
        market_context: dict,
        strategy: dict,
        image_paths: list[str],
    ) -> str:
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

        return f"""
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

    def _extract_json_object(self, text: str) -> dict[str, Any]:
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

    def _build_template_copy(
        self,
        confirmed_product: dict,
        market_context: dict,
        strategy: dict,
    ) -> dict[str, Any]:
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

        deduped_tags = []
        seen = set()
        for tag in tags:
            normalized = str(tag).strip()
            if normalized and normalized not in seen:
                deduped_tags.append(normalized)
                seen.add(normalized)

        return {
            "title": title,
            "description": description,
            "tags": deduped_tags[:5],
        }

    async def _generate_copy_with_openai(
        self,
        confirmed_product: dict,
        market_context: dict,
        strategy: dict,
        image_paths: list[str],
    ) -> dict[str, Any]:
        if not settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY is not configured")

        prompt = self._build_copy_prompt(
            confirmed_product=confirmed_product,
            market_context=market_context,
            strategy=strategy,
            image_paths=image_paths,
        )

        headers = {
            "Authorization": f"Bearer {settings.openai_api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": settings.openai_listing_model,
            "messages": [
                {
                    "role": "system",
                    "content": "You generate structured JSON listing drafts.",
                },
                {
                    "role": "user",
                    "content": prompt,
                },
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
                return self._extract_json_object(text)

            except httpx.HTTPStatusError as e:
                last_error = e
                if e.response.status_code == 429:
                    continue
                raise

        raise last_error if last_error else ValueError("OpenAI request failed")

    async def _generate_copy_with_gemini(
        self,
        confirmed_product: dict,
        market_context: dict,
        strategy: dict,
        image_paths: list[str],
    ) -> dict[str, Any]:
        if not getattr(settings, "gemini_api_key", None):
            raise ValueError("GEMINI_API_KEY is not configured")

        gemini_model = getattr(settings, "gemini_listing_model", None)
        if not gemini_model:
            raise ValueError("GEMINI_LISTING_MODEL is not configured")

        prompt = self._build_copy_prompt(
            confirmed_product=confirmed_product,
            market_context=market_context,
            strategy=strategy,
            image_paths=image_paths,
        )

        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{gemini_model}:generateContent"
            f"?key={settings.gemini_api_key}"
        )

        payload = {
            "contents": [
                {
                    "parts": [{"text": prompt}],
                }
            ],
            "generationConfig": {
                "temperature": 0.3,
            },
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
        return self._extract_json_object(text)

    async def _generate_copy_with_solar(
        self,
        confirmed_product: dict,
        market_context: dict,
        strategy: dict,
        image_paths: list[str],
    ) -> dict[str, Any]:
        if not getattr(settings, "upstage_api_key", None):
            raise ValueError("UPSTAGE_API_KEY is not configured")

        solar_model = getattr(settings, "solar_listing_model", None)
        if not solar_model:
            raise ValueError("SOLAR_LISTING_MODEL is not configured")

        prompt = self._build_copy_prompt(
            confirmed_product=confirmed_product,
            market_context=market_context,
            strategy=strategy,
            image_paths=image_paths,
        )

        headers = {
            "Authorization": f"Bearer {settings.upstage_api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": solar_model,
            "messages": [
                {
                    "role": "system",
                    "content": "You generate structured JSON listing drafts.",
                },
                {
                    "role": "user",
                    "content": prompt,
                },
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
        return self._extract_json_object(text)

    async def _generate_copy(
        self,
        confirmed_product: dict,
        market_context: dict,
        strategy: dict,
        image_paths: list[str],
    ) -> dict[str, Any]:
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
                    return await self._generate_copy_with_openai(
                        confirmed_product=confirmed_product,
                        market_context=market_context,
                        strategy=strategy,
                        image_paths=image_paths,
                    )

                if provider == "gemini":
                    return await self._generate_copy_with_gemini(
                        confirmed_product=confirmed_product,
                        market_context=market_context,
                        strategy=strategy,
                        image_paths=image_paths,
                    )

                if provider == "solar":
                    return await self._generate_copy_with_solar(
                        confirmed_product=confirmed_product,
                        market_context=market_context,
                        strategy=strategy,
                        image_paths=image_paths,
                    )

            except Exception:
                continue

        return self._build_template_copy(
            confirmed_product=confirmed_product,
            market_context=market_context,
            strategy=strategy,
        )

    async def build_canonical_listing(
        self,
        confirmed_product: dict,
        market_context: dict,
        strategy: dict,
        image_paths: list[str],
    ) -> dict:
        llm_result = await self._generate_copy(
            confirmed_product=confirmed_product,
            market_context=market_context,
            strategy=strategy,
            image_paths=image_paths,
        )

        title = llm_result.get("title") or f"{confirmed_product.get('model', '상품')} 판매합니다"
        description = llm_result.get("description") or "AI가 생성한 판매글 초안"
        tags = llm_result.get("tags") or [confirmed_product.get("model", "상품")]

        if not isinstance(tags, list):
            tags = [str(tags)]

        tags = [str(tag).strip() for tag in tags if str(tag).strip()][:5]

        return {
            "title": title,
            "description": description,
            "price": strategy.get("recommended_price", 0),
            "tags": tags,
            "images": image_paths,
            "strategy": strategy.get("goal", "fast_sell"),
            "product": confirmed_product,
        }

    async def build_listing_package(
        self,
        confirmed_product: dict,
        image_paths: list[str],
    ) -> dict:
        market_context = await self.build_market_context(confirmed_product)

        strategy = await self.build_pricing_strategy(
            confirmed_product,
            market_context,
        )

        canonical_listing = await self.build_canonical_listing(
            confirmed_product,
            market_context,
            strategy,
            image_paths,
        )

        return {
            "market_context": market_context,
            "strategy": strategy,
            "canonical_listing": canonical_listing,
        }