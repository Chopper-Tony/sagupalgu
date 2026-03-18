from dataclasses import dataclass, asdict, field
from datetime import datetime
from typing import Any, Literal


SessionStatus = Literal[
    "session_created",
    "images_uploaded",
    "awaiting_product_confirmation",
    "product_confirmed",
    "market_analyzing",
    "draft_generated",
    "awaiting_publish_approval",
    "publishing",
    "completed",
    "publishing_failed",
    "failed",
]

PlatformName = Literal["joongna", "bunjang", "daangn", "sagupalgu_market"]
AuthType = Literal["id_password", "session_file", "emulator_session"]


def _json_safe(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()

    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}

    if isinstance(value, list):
        return [_json_safe(v) for v in value]

    return value


@dataclass
class SellSession:
    id: str
    user_id: str
    status: SessionStatus
    strategy_goal: str | None = None
    selected_platforms_jsonb: list[str] = field(default_factory=list)
    product_data_jsonb: dict[str, Any] = field(default_factory=dict)
    listing_data_jsonb: dict[str, Any] = field(default_factory=dict)
    workflow_meta_jsonb: dict[str, Any] = field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def to_record(self) -> dict[str, Any]:
        data = asdict(self)
        return _json_safe(data)