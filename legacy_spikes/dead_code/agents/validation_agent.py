from app.state.sell_session_state import SellSessionState

class ValidationAgent:
    async def run(self, state: SellSessionState) -> SellSessionState:
        listing = state.get("canonical_listing") or {}
        warnings = []
        if not listing.get("title"):
            warnings.append("title_missing")
        if not listing.get("description"):
            warnings.append("description_missing")

        state["validation_result"] = {
            "warnings": warnings,
            "valid": len(warnings) == 0,
        }
        state["status"] = "awaiting_publish_approval"
        return state
