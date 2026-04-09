"""마켓 API — completed 세션의 상품 목록 공개 조회. 인증 불필요."""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, Query

from app.dependencies import get_session_repository
from app.repositories.session_repository import SessionRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/market", tags=["market"])


@router.get("")
async def list_market_items(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    repo: SessionRepository = Depends(get_session_repository),
) -> dict[str, Any]:
    """completed 상태 세션의 상품 목록을 반환한다."""
    items, total = repo.list_completed(limit=limit, offset=offset)
    return {
        "items": [_to_market_item(row) for row in items],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


def _to_market_item(session: dict) -> dict[str, Any]:
    """DB 레코드 → 마켓 카드용 경량 응답."""
    product_data = session.get("product_data_jsonb") or {}
    listing_data = session.get("listing_data_jsonb") or {}
    workflow_meta = session.get("workflow_meta_jsonb") or {}
    canonical = listing_data.get("canonical_listing") or {}

    publish_results = workflow_meta.get("publish_results") or {}
    published_platforms = [
        p for p, detail in publish_results.items()
        if isinstance(detail, dict) and detail.get("success")
    ]

    return {
        "session_id": session.get("id"),
        "title": canonical.get("title", ""),
        "description": canonical.get("description", ""),
        "price": canonical.get("price", 0),
        "image_urls": product_data.get("image_paths") or [],
        "tags": canonical.get("tags") or [],
        "published_platforms": published_platforms,
        "created_at": session.get("created_at"),
    }
