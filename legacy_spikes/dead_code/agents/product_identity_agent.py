from app.services.product_service import ProductService
from app.state.sell_session_state import SellSessionState

class ProductIdentityAgent:
    def __init__(self, product_service: ProductService):
        self.product_service = product_service

    async def run(self, state: SellSessionState) -> SellSessionState:
        result = await self.product_service.identify_product(state.get("processed_image_paths", []))
        state["product_candidates"] = result.candidates
        state["status"] = "awaiting_product_confirmation"
        return state
