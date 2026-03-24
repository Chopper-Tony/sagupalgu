from app.state.sell_session_state import SellSessionState
from app.crawlers.joongna_crawler import joongna_crawler_tool
from app.crawlers.bunjang_crawler import bunjang_crawler_tool
from app.crawlers.daangn_crawler import daangn_crawler_tool
from app.tools.rag_price_retrieval import rag_price_retrieval
from app.tools.market_price_aggregator import market_price_aggregator

class MarketIntelligenceAgent:
    async def run(self, state: SellSessionState) -> SellSessionState:
        product = state.get("confirmed_product") or {}
        crawler_results = [
            await joongna_crawler_tool(product),
            await bunjang_crawler_tool(product),
            await daangn_crawler_tool(product),
        ]
        aggregated = market_price_aggregator(crawler_results)
        rag = await rag_price_retrieval(product)
        state["market_context"] = {**aggregated, **rag}
        state["status"] = "market_analyzing"
        return state
