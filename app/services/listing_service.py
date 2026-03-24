from app.domain.schemas import CanonicalListingSchema
from app.services.listing_llm import generate_copy
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

        llm_result = await generate_copy(
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