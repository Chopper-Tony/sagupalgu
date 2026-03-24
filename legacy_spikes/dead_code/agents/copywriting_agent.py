from app.state.sell_session_state import SellSessionState
from app.services.listing_service import ListingService

class CopywritingAgent:
    def __init__(self, listing_service: ListingService):
        self.listing_service = listing_service

    async def run(self, state: SellSessionState) -> SellSessionState:
        canonical = await self.listing_service.build_canonical_listing(
            confirmed_product=state.get("confirmed_product") or {},
            market_context=state.get("market_context") or {},
        )
        state["canonical_listing"] = canonical
        state["status"] = "draft_generated"
        return state
