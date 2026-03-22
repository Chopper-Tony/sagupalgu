from __future__ import annotations

import asyncio
import inspect
from typing import Any, Dict, List, Optional

from app.graph.seller_copilot_graph import seller_copilot_graph
from app.graph.seller_copilot_state import (
    SellerCopilotState,
    create_initial_state,
)


def _to_plain_dict(value: Any) -> Dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value

    result: Dict[str, Any] = {}
    for attr in dir(value):
        if attr.startswith("_"):
            continue
        try:
            attr_value = getattr(value, attr)
        except Exception:
            continue
        if callable(attr_value):
            continue
        result[attr] = attr_value
    return result


def _run_sync_or_async_callable(func: Any, **kwargs) -> Any:
    if func is None or not callable(func):
        return None

    try:
        sig = inspect.signature(func)
        accepted_kwargs = {
            key: value
            for key, value in kwargs.items()
            if key in sig.parameters
        }
    except Exception:
        accepted_kwargs = kwargs

    try:
        result = func(**accepted_kwargs)
    except TypeError:
        return None
    except Exception:
        return None

    if inspect.isawaitable(result):
        try:
            return asyncio.run(result)
        except RuntimeError:
            loop = asyncio.new_event_loop()
            try:
                return loop.run_until_complete(result)
            finally:
                loop.close()

    return result


def _call_method_if_exists(service: Any, method_names: List[str], **kwargs) -> Any:
    if service is None:
        return None

    for method_name in method_names:
        method = getattr(service, method_name, None)
        if method is None or not callable(method):
            continue

        result = _run_sync_or_async_callable(method, **kwargs)
        if result is not None:
            return result

    return None


class SellerCopilotServiceAdapter:
    def __init__(
        self,
        product_service: Any = None,
        market_service: Any = None,
        listing_service: Any = None,
    ):
        self.product_service = product_service or self._try_create_product_service()
        self.market_service = market_service or self._try_create_market_service()
        self.listing_service = listing_service or self._try_create_listing_service()

    def _try_create_product_service(self) -> Any:
        try:
            from app.services.product_service import ProductService
            return ProductService()
        except Exception:
            return None

    def _try_create_market_service(self) -> Any:
        try:
            from app.services.market_service import MarketService
            return MarketService()
        except Exception:
            return None

    def _try_create_listing_service(self) -> Any:
        try:
            from app.services.listing_service import ListingService
            return ListingService()
        except Exception:
            return None

    def product_identity_hook(self, state: SellerCopilotState) -> Dict[str, Any]:
        result = _call_method_if_exists(
            self.product_service,
            ["analyze_product", "analyze", "analyze_images", "run"],
            session_id=state.get("session_id"),
            image_paths=state.get("image_paths"),
            user_product_input=state.get("user_product_input"),
        )

        data = _to_plain_dict(result)
        if not data:
            return {}

        updates: Dict[str, Any] = {}

        if "product_candidates" in data:
            updates["product_candidates"] = data["product_candidates"]
        elif "candidates" in data:
            updates["product_candidates"] = data["candidates"]

        if "confirmed_product" in data and data["confirmed_product"]:
            updates["confirmed_product"] = data["confirmed_product"]
            updates["needs_user_input"] = False

        if "needs_user_input" in data:
            updates["needs_user_input"] = bool(data["needs_user_input"])

        if "clarification_prompt" in data:
            updates["clarification_prompt"] = data["clarification_prompt"]

        if "analysis_source" in data:
            updates["analysis_source"] = data["analysis_source"]

        return updates

    def market_intelligence_hook(self, state: SellerCopilotState) -> Dict[str, Any]:
        confirmed_product = state.get("confirmed_product") or {}

        result = _call_method_if_exists(
            self.market_service,
            ["get_market_context", "analyze_market", "analyze", "run"],
            session_id=state.get("session_id"),
            confirmed_product=confirmed_product,
            product=confirmed_product,
            brand=confirmed_product.get("brand"),
            model=confirmed_product.get("model"),
            category=confirmed_product.get("category"),
            queries=state.get("search_queries"),
        )

        data = _to_plain_dict(result)
        if not data:
            return {}

        if "market_context" in data:
            return {"market_context": data["market_context"]}

        if any(k in data for k in ["price_band", "median_price", "sample_count", "crawler_sources"]):
            return {
                "market_context": {
                    "price_band": data.get("price_band", []),
                    "median_price": data.get("median_price"),
                    "sample_count": data.get("sample_count", 0),
                    "crawler_sources": data.get("crawler_sources", []),
                }
            }

        return {}

    def copywriting_hook(self, state: SellerCopilotState) -> Dict[str, Any]:
        confirmed_product = state.get("confirmed_product") or {}
        market_context = state.get("market_context") or {}
        strategy = state.get("strategy") or {}

        result = _call_method_if_exists(
            self.listing_service,
            ["build_canonical_listing", "generate_listing", "create_listing", "run"],
            session_id=state.get("session_id"),
            confirmed_product=confirmed_product,
            product=confirmed_product,
            market_context=market_context,
            strategy=strategy,
            image_paths=state.get("image_paths"),
            selected_platforms=state.get("selected_platforms"),
        )

        data = _to_plain_dict(result)
        if not data:
            return {}

        updates: Dict[str, Any] = {}

        if "canonical_listing" in data and data["canonical_listing"]:
            updates["canonical_listing"] = data["canonical_listing"]
            return updates

        if all(k in data for k in ["title", "description"]):
            updates["canonical_listing"] = {
                "title": data.get("title", ""),
                "description": data.get("description", ""),
                "tags": data.get("tags", []),
                "price": data.get("price", strategy.get("recommended_price", 0)),
                "images": data.get("images", state.get("image_paths", [])),
                "strategy": strategy.get("goal", "fast_sell"),
                "product": {
                    "brand": confirmed_product.get("brand", ""),
                    "model": confirmed_product.get("model", ""),
                    "category": confirmed_product.get("category", ""),
                    "confidence": confirmed_product.get("confidence", 0.0),
                    "source": confirmed_product.get("source", ""),
                    "storage": confirmed_product.get("storage", ""),
                },
            }

        return updates

    def package_builder_hook(self, state: SellerCopilotState) -> Dict[str, Any]:
        canonical_listing = state.get("canonical_listing") or {}
        if not canonical_listing:
            return {}

        result = _call_method_if_exists(
            self.listing_service,
            ["build_platform_packages", "prepare_platform_packages", "build_publish_packages"],
            session_id=state.get("session_id"),
            canonical_listing=canonical_listing,
            selected_platforms=state.get("selected_platforms"),
        )

        data = _to_plain_dict(result)
        if not data:
            return {}

        if "platform_packages" in data:
            return {"platform_packages": data["platform_packages"]}

        return {}


class SellerCopilotRunner:
    def __init__(
        self,
        product_service: Any = None,
        market_service: Any = None,
        listing_service: Any = None,
    ):
        self.adapter = SellerCopilotServiceAdapter(
            product_service=product_service,
            market_service=market_service,
            listing_service=listing_service,
        )

    def build_initial_state(
        self,
        session_id: str,
        image_paths: List[str],
        selected_platforms: Optional[List[str]] = None,
        user_product_input: Optional[Dict[str, Any]] = None,
        product_candidates: Optional[List[Dict[str, Any]]] = None,
        market_context: Optional[Dict[str, Any]] = None,
    ) -> SellerCopilotState:
        state = create_initial_state(
            session_id=session_id,
            image_paths=image_paths,
            selected_platforms=selected_platforms,
            user_product_input=user_product_input,
        )

        if product_candidates:
            state["product_candidates"] = product_candidates

        if market_context:
            state["market_context"] = market_context

        state["_product_identity_hook_result"] = self.adapter.product_identity_hook(state)
        state["_market_intelligence_hook_result"] = self.adapter.market_intelligence_hook(state)
        state["_copywriting_hook_result"] = self.adapter.copywriting_hook(state)
        state["_package_builder_hook_result"] = self.adapter.package_builder_hook(state)

        return state

    def run(
        self,
        session_id: str,
        image_paths: List[str],
        selected_platforms: Optional[List[str]] = None,
        user_product_input: Optional[Dict[str, Any]] = None,
        product_candidates: Optional[List[Dict[str, Any]]] = None,
        market_context: Optional[Dict[str, Any]] = None,
    ) -> SellerCopilotState:
        initial_state = self.build_initial_state(
            session_id=session_id,
            image_paths=image_paths,
            selected_platforms=selected_platforms,
            user_product_input=user_product_input,
            product_candidates=product_candidates,
            market_context=market_context,
        )

        final_state = seller_copilot_graph.invoke(initial_state)
        return final_state


seller_copilot_runner = SellerCopilotRunner()