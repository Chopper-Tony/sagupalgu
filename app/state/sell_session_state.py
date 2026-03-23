from typing import TypedDict, Any

from app.domain.session_status import SessionStatus as StateStatus  # re-export alias


class SellSessionState(TypedDict, total=False):
    session_id: str
    user_id: str
    status: StateStatus

    image_paths: list[str]
    processed_image_paths: list[str]

    product_candidates: list[dict]
    confirmed_product: dict | None

    market_context: dict[str, Any] | None
    canonical_listing: dict | None
    platform_packages: dict[str, Any] | None

    selected_platforms: list[str]
    validation_result: dict[str, Any] | None
    publish_results: dict[str, Any] | None
    last_error: dict[str, Any] | None