from app.state.sell_session_state import SellSessionState
from app.tools.image_preprocess import image_preprocess
from app.services.product_service import ProductService
from app.services.listing_service import ListingService
from app.agents.product_identity_agent import ProductIdentityAgent
from app.agents.market_intelligence_agent import MarketIntelligenceAgent
from app.agents.pricing_agent import PricingStrategyAgent
from app.agents.copywriting_agent import CopywritingAgent
from app.agents.validation_agent import ValidationAgent

product_identity_agent = ProductIdentityAgent(ProductService())
market_agent = MarketIntelligenceAgent()
pricing_agent = PricingStrategyAgent()
copywriting_agent = CopywritingAgent(ListingService())
validation_agent = ValidationAgent()

async def preprocess_node(state: SellSessionState) -> SellSessionState:
    state["processed_image_paths"] = await image_preprocess(state.get("image_paths", []))
    return state

async def product_identity_node(state: SellSessionState) -> SellSessionState:
    return await product_identity_agent.run(state)

async def market_intelligence_node(state: SellSessionState) -> SellSessionState:
    return await market_agent.run(state)

async def pricing_node(state: SellSessionState) -> SellSessionState:
    return await pricing_agent.run(state)

async def copywriting_node(state: SellSessionState) -> SellSessionState:
    return await copywriting_agent.run(state)

async def validation_node(state: SellSessionState) -> SellSessionState:
    return await validation_agent.run(state)
