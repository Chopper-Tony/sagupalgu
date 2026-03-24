import asyncio
from typing import Any

import httpx

from app.core.config import settings
from app.domain.schemas import CanonicalListingSchema
from app.services.listing_prompt import build_copy_prompt, extract_json_object
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
                return extract_json_object(text)

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
        return extract_json_object(text)

    async def _generate_copy_with_solar(
        self,
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
        return extract_json_object(text)

    async def _generate_copy(
        self,
        confirmed_product: dict,
        market_context: dict,
        strategy: dict,
        image_paths: list[str],
        tool_calls_context: str = "",
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
                        tool_calls_context=tool_calls_context,
                    )

                if provider == "gemini":
                    return await self._generate_copy_with_gemini(
                        confirmed_product=confirmed_product,
                        market_context=market_context,
                        strategy=strategy,
                        image_paths=image_paths,
                        tool_calls_context=tool_calls_context,
                    )

                if provider == "solar":
                    return await self._generate_copy_with_solar(
                        confirmed_product=confirmed_product,
                        market_context=market_context,
                        strategy=strategy,
                        image_paths=image_paths,
                        tool_calls_context=tool_calls_context,
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
        tool_calls: list = None,
    ) -> dict:
        # Build tool_calls_context string from the list for prompt augmentation
        tool_calls_context = ""
        if tool_calls:
            lines = []
            for tc in tool_calls:
                tool_name = tc.get("tool_name", "unknown")
                success = tc.get("success", False)
                lines.append(f"- {tool_name}: {'success' if success else 'failed'}")
            tool_calls_context = "\n".join(lines)

        llm_result = await self._generate_copy(
            confirmed_product=confirmed_product,
            market_context=market_context,
            strategy=strategy,
            image_paths=image_paths,
            tool_calls_context=tool_calls_context,
        )

        return CanonicalListingSchema.from_llm_result(
            llm_result,
            confirmed_product=confirmed_product,
            strategy=strategy,
            image_paths=image_paths,
        ).model_dump()

    async def rewrite_listing(
        self,
        canonical_listing: dict,
        rewrite_instruction: str,
        confirmed_product: dict,
        market_context: dict,
        strategy: dict,
    ) -> dict:
        """사용자 피드백 기반 판매글 재작성.

        build_canonical_listing()과 별도 유스케이스:
        - build_canonical_listing: 시세·상품 정보로 최초 생성
        - rewrite_listing: 기존 draft + 사용자 피드백으로 수정
        """
        image_paths = canonical_listing.get("images") or []

        rewrite_context = (
            f"[재작성 요청]\n"
            f"기존 제목: {canonical_listing.get('title', '')}\n"
            f"기존 설명: {(canonical_listing.get('description') or '')[:200]}\n"
            f"수정 지시: {rewrite_instruction}\n"
            f"위 지시사항을 반영해 판매글을 개선하라."
        )

        llm_result = await self._generate_copy(
            confirmed_product=confirmed_product,
            market_context=market_context,
            strategy=strategy,
            image_paths=image_paths,
            tool_calls_context=rewrite_context,
        )

        return CanonicalListingSchema.from_rewrite_result(
            llm_result,
            previous=canonical_listing,
            strategy=strategy,
        ).model_dump()

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