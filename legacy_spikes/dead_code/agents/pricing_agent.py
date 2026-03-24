from app.state.sell_session_state import SellSessionState

class PricingStrategyAgent:
    async def run(self, state: SellSessionState) -> SellSessionState:
        market_context = state.get("market_context") or {}
        median = market_context.get("median_price", 0)
        market_context["recommended_price"] = median
        state["market_context"] = market_context
        return state
