"""
ListingService — 판매글 생성·재작성 오케스트레이터.

책임: LLM 호출 조율 + CanonicalListingSchema 검증.
순수 로직은 listing_prompt.py에 위임.
LLM HTTP 호출은 listing_llm.py에 위임.
"""
from app.domain.schemas import CanonicalListingSchema
from app.services.listing_llm import generate_copy
from app.services.listing_prompt import (
    build_pricing_strategy,
    build_rewrite_context,
    build_tool_calls_context,
)
from app.services.market.market_service import MarketService


class ListingService:
    def __init__(self):
        self.market_service = MarketService()

    async def build_market_context(self, confirmed_product: dict) -> dict:
        return await self.market_service.analyze_market(confirmed_product)

    async def build_pricing_strategy(
        self, confirmed_product: dict, market_context: dict,
    ) -> dict:
        median_price = market_context.get("median_price") or 0
        return build_pricing_strategy(median_price)

    async def build_canonical_listing(
        self,
        confirmed_product: dict,
        market_context: dict,
        strategy: dict,
        image_paths: list[str],
        tool_calls: list = None,
    ) -> dict:
        tool_calls_context = build_tool_calls_context(tool_calls or [])

        llm_result = await generate_copy(
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
        """사용자 피드백 기반 판매글 재작성."""
        rewrite_context = build_rewrite_context(canonical_listing, rewrite_instruction)

        llm_result = await generate_copy(
            confirmed_product=confirmed_product,
            market_context=market_context,
            strategy=strategy,
            image_paths=canonical_listing.get("images") or [],
            tool_calls_context=rewrite_context,
        )

        return CanonicalListingSchema.from_rewrite_result(
            llm_result,
            previous=canonical_listing,
            strategy=strategy,
        ).model_dump()

    async def build_listing_package(
        self, confirmed_product: dict, image_paths: list[str],
    ) -> dict:
        market_context = await self.build_market_context(confirmed_product)
        strategy = await self.build_pricing_strategy(confirmed_product, market_context)
        canonical_listing = await self.build_canonical_listing(
            confirmed_product, market_context, strategy, image_paths,
        )
        return {
            "market_context": market_context,
            "strategy": strategy,
            "canonical_listing": canonical_listing,
        }
