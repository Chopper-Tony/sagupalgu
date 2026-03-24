"""
세션 상태 머신 단일 진실 원천(Single Source of Truth).

SessionStatus, 전이 규칙, 다음 액션 해석 로직을 한 곳에서 관리.
"""
from __future__ import annotations

from typing import Literal, Optional

from app.domain.exceptions import InvalidStateTransitionError

# ── 모든 세션 상태 ──────────────────────────────────────────────────
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
    "failed",
    "publishing_failed",
    "awaiting_sale_status_update",
    "optimization_suggested",
]

# ── 허용 전이 규칙 ──────────────────────────────────────────────────
ALLOWED_TRANSITIONS: dict[str, list[str]] = {
    "session_created":               ["images_uploaded"],
    "images_uploaded":               ["awaiting_product_confirmation"],
    "awaiting_product_confirmation": ["product_confirmed"],
    "product_confirmed":             ["market_analyzing", "draft_generated"],
    "market_analyzing":              ["draft_generated", "failed"],
    "draft_generated":               ["awaiting_publish_approval", "draft_generated"],
    "awaiting_publish_approval":     ["publishing"],
    "publishing":                    ["completed", "publishing_failed"],
    "completed":                     ["awaiting_sale_status_update"],
    "awaiting_sale_status_update":   ["optimization_suggested", "awaiting_sale_status_update"],
    "optimization_suggested":        [],
    "publishing_failed":             ["awaiting_publish_approval"],
    "failed":                        [],
}

TERMINAL_STATUSES: frozenset[str] = frozenset(
    {"completed", "failed", "publishing_failed", "optimization_suggested"}
)


def is_terminal_status(status: str) -> bool:
    return status in TERMINAL_STATUSES


def assert_allowed_transition(current: str, next_status: str) -> None:
    """허용되지 않은 상태 전이 시 InvalidStateTransitionError 발생."""
    allowed = ALLOWED_TRANSITIONS.get(current, [])
    if next_status not in allowed:
        raise InvalidStateTransitionError(
            f"허용되지 않은 상태 전이: '{current}' → '{next_status}' "
            f"(허용: {allowed})"
        )


def resolve_next_action(status: str, needs_user_input: bool = False) -> Optional[str]:
    """현재 상태 → UI가 다음에 호출해야 할 액션 이름."""
    if status == "awaiting_product_confirmation":
        return "provide_product_info" if needs_user_input else "confirm_product"
    _mapping: dict[str, str] = {
        "session_created":             "upload_images",
        "images_uploaded":             "analyze",
        "product_confirmed":           "generate_listing",
        "draft_generated":             "prepare_publish",
        "awaiting_publish_approval":   "publish",
        "publishing":                  "poll_status",
        "completed":                   "done",
        "publishing_failed":           "retry_or_edit",
        "awaiting_sale_status_update": "update_sale_status",
        "optimization_suggested":      "review_optimization",
    }
    return _mapping.get(status)
