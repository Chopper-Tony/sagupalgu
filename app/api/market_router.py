"""마켓 API — completed 세션의 상품 목록 공개 조회. 인증 불필요."""
from __future__ import annotations

import logging
import os
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.dependencies import get_session_repository
from app.repositories.session_repository import SessionRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/market", tags=["market"])


# ── 목록 (검색 + 가격 필터) ──────────────────────────────


@router.get("")
async def list_market_items(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    q: str | None = Query(default=None, description="키워드 검색 (제목, 태그)"),
    min_price: int | None = Query(default=None, ge=0, description="최소 가격"),
    max_price: int | None = Query(default=None, ge=0, description="최대 가격"),
    repo: SessionRepository = Depends(get_session_repository),
) -> dict[str, Any]:
    """completed 상태 세션의 상품 목록을 반환한다. 검색/가격 필터 지원."""
    has_filter = q is not None or min_price is not None or max_price is not None

    if has_filter:
        items, total = repo.search_completed(
            q=q, min_price=min_price, max_price=max_price,
            limit=limit, offset=offset,
        )
    else:
        items, total = repo.list_completed(limit=limit, offset=offset)

    return {
        "items": [_to_market_item(row) for row in items],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


# ── 상세 ────────────────────────────────────────────────


@router.get("/{session_id}")
async def get_market_item(
    session_id: str,
    repo: SessionRepository = Depends(get_session_repository),
) -> dict[str, Any]:
    """completed 상태 세션의 상품 상세 정보를 반환한다."""
    row = repo.get_completed_by_id(session_id)
    if not row:
        raise HTTPException(status_code=404, detail="상품을 찾을 수 없습니다.")
    return _to_market_detail(row)


# ── 구매 문의 ─────────────────────────────────────────


class InquiryRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=50)
    contact: str = Field(..., min_length=1, max_length=100)
    message: str = Field(..., min_length=1, max_length=1000)


@router.post("/{session_id}/inquiry")
async def submit_inquiry(
    session_id: str,
    body: InquiryRequest,
    repo: SessionRepository = Depends(get_session_repository),
) -> dict[str, Any]:
    """구매자가 판매자에게 문의를 보낸다. Discord 웹훅으로 전달."""
    row = repo.get_completed_by_id(session_id)
    if not row:
        raise HTTPException(status_code=404, detail="상품을 찾을 수 없습니다.")

    canonical = (row.get("listing_data_jsonb") or {}).get("canonical_listing") or {}
    title = canonical.get("title", "(제목 없음)")

    sent = await _send_inquiry_discord(
        session_id=session_id,
        product_title=title,
        name=body.name,
        contact=body.contact,
        message=body.message,
    )

    return {"success": True, "discord_sent": sent}


# ── 헬퍼 ───────────────────────────────────────────────


def _to_market_item(session: dict) -> dict[str, Any]:
    """DB 레코드 -> 마켓 카드용 경량 응답."""
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
        "description": (canonical.get("description") or "")[:200],
        "price": canonical.get("price", 0),
        "image_urls": product_data.get("image_paths") or [],
        "tags": canonical.get("tags") or [],
        "published_platforms": published_platforms,
        "created_at": session.get("created_at"),
    }


def _to_market_detail(session: dict) -> dict[str, Any]:
    """DB 레코드 -> 마켓 상세 응답 (description 전체 + 플랫폼 URL)."""
    product_data = session.get("product_data_jsonb") or {}
    listing_data = session.get("listing_data_jsonb") or {}
    workflow_meta = session.get("workflow_meta_jsonb") or {}
    canonical = listing_data.get("canonical_listing") or {}

    publish_results = workflow_meta.get("publish_results") or {}
    platform_links: list[dict[str, str]] = []
    for platform, detail in publish_results.items():
        if isinstance(detail, dict) and detail.get("success"):
            url = detail.get("external_url") or detail.get("listing_url") or ""
            platform_links.append({"platform": platform, "url": url})

    return {
        "session_id": session.get("id"),
        "title": canonical.get("title", ""),
        "description": canonical.get("description", ""),
        "price": canonical.get("price", 0),
        "image_urls": product_data.get("image_paths") or [],
        "tags": canonical.get("tags") or [],
        "platform_links": platform_links,
        "created_at": session.get("created_at"),
    }


async def _send_inquiry_discord(
    session_id: str,
    product_title: str,
    name: str,
    contact: str,
    message: str,
) -> bool:
    """Discord 웹훅으로 구매 문의 알림을 전송한다."""
    try:
        import httpx

        webhook_url = os.getenv("DISCORD_WEBHOOK_URL")
        if not webhook_url:
            logger.info("DISCORD_WEBHOOK_URL 미설정, 문의 알림 생략 session=%s", session_id)
            return False

        payload = {
            "embeds": [{
                "title": "[사구팔구] 구매 문의",
                "color": 0x00BFFF,
                "fields": [
                    {"name": "상품", "value": product_title, "inline": True},
                    {"name": "session_id", "value": session_id, "inline": True},
                    {"name": "문의자", "value": name, "inline": True},
                    {"name": "연락처", "value": contact, "inline": True},
                    {"name": "메시지", "value": message, "inline": False},
                ],
            }]
        }
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(webhook_url, json=payload)
            resp.raise_for_status()
        logger.info("inquiry_discord_sent session=%s name=%s", session_id, name)
        return True

    except Exception as e:
        logger.warning("inquiry_discord_failed session=%s error=%s", session_id, e, exc_info=True)
        return False
