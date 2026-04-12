"""마켓 API — 공개 상품 조회 + 판매자 상품 관리."""
from __future__ import annotations

import logging
import os
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.core.auth import AuthenticatedUser, get_current_user
from app.dependencies import get_inquiry_repository, get_session_repository, get_session_service
from app.services.session_service import SessionService
from app.repositories.inquiry_repository import InquiryRepository
from app.repositories.session_repository import (
    SALE_STATUS_TRANSITIONS,
    SessionRepository,
    _get_sale_status,
)

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
    sale_status: str | None = Query(default=None, description="판매 상태 필터 (available/reserved/sold)"),
    category: str | None = Query(default=None, description="카테고리 필터"),
    repo: SessionRepository = Depends(get_session_repository),
) -> dict[str, Any]:
    """completed 상태 세션의 상품 목록을 반환한다. 검색/가격/판매상태/카테고리 필터 지원."""
    has_filter = q is not None or min_price is not None or max_price is not None

    if has_filter:
        items, total = repo.search_completed(
            q=q, min_price=min_price, max_price=max_price,
            limit=limit, offset=offset,
        )
    else:
        items, total = repo.list_completed(limit=limit, offset=offset)

    # 판매 상태 필터 (Python 레벨 — 데이터 규모가 작으므로 허용)
    if sale_status:
        items = [row for row in items if _get_sale_status(row) == sale_status]
        total = len(items)

    # 카테고리 필터
    if category:
        items = [row for row in items if _get_category(row) == category]
        total = len(items)

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
    inquiry_repo: InquiryRepository = Depends(get_inquiry_repository),
) -> dict[str, Any]:
    """구매자가 판매자에게 문의를 보낸다. DB 저장 + Discord 웹훅 알림."""
    row = repo.get_completed_by_id(session_id)
    if not row:
        raise HTTPException(status_code=404, detail="상품을 찾을 수 없습니다.")

    # 판매완료 상품은 문의 불가
    if _get_sale_status(row) == "sold":
        raise HTTPException(status_code=400, detail="판매가 완료된 상품입니다.")

    canonical = (row.get("listing_data_jsonb") or {}).get("canonical_listing") or {}
    title = canonical.get("title", "(제목 없음)")

    # DB 저장
    inquiry = inquiry_repo.create(
        listing_id=session_id,
        buyer_name=body.name,
        buyer_contact=body.contact,
        message=body.message,
    )
    logger.info("inquiry_created listing=%s inquiry=%s", session_id, inquiry.get("id"))

    # Discord 알림 (보조 — 실패해도 OK)
    sent = await _send_inquiry_discord(
        session_id=session_id,
        product_title=title,
        name=body.name,
        contact=body.contact,
        message=body.message,
    )

    return {"success": True, "inquiry_id": inquiry.get("id"), "discord_sent": sent}


# ── 판매자 전용 (인증 필요) ─────────────────────────────


class SaleStatusUpdateRequest(BaseModel):
    sale_status: Literal["available", "reserved", "sold"]


class ReplyRequest(BaseModel):
    reply: str = Field(..., min_length=1, max_length=2000)


class RelistRequest(BaseModel):
    new_price: int | None = Field(default=None, ge=0, description="변경할 가격 (없으면 기존 가격 유지)")


@router.get("/my-listings", tags=["seller"])
async def list_my_listings(
    sale_status_filter: str | None = Query(default=None, description="판매 상태 필터"),
    user: AuthenticatedUser = Depends(get_current_user),
    repo: SessionRepository = Depends(get_session_repository),
    inquiry_repo: InquiryRepository = Depends(get_inquiry_repository),
) -> dict[str, Any]:
    """내 상품 목록 (판매자 대시보드용). 인증 필요. inquiry_count 포함."""
    items = repo.list_by_user(user.user_id, sale_status_filter=sale_status_filter)
    result = []
    for row in items:
        item = _to_my_listing_item(row)
        sid = row.get("id", "")
        item["inquiry_count"] = inquiry_repo.count_by_listing(sid)
        item["unread_inquiry_count"] = inquiry_repo.count_unread(sid)
        result.append(item)
    return {
        "items": result,
        "total": len(result),
    }


@router.patch("/my-listings/{session_id}/status", tags=["seller"])
async def update_listing_sale_status(
    session_id: str,
    body: SaleStatusUpdateRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    repo: SessionRepository = Depends(get_session_repository),
) -> dict[str, Any]:
    """마켓 상품의 판매 상태를 변경한다. 인증 필요, 소유권 검증."""
    new_status = body.sale_status
    allowed_from = [
        k for k, v in SALE_STATUS_TRANSITIONS.items() if new_status in v
    ]
    if not allowed_from:
        raise HTTPException(status_code=400, detail=f"'{new_status}'로 전이 가능한 상태가 없습니다")

    result = repo.update_sale_status(
        session_id=session_id,
        user_id=user.user_id,
        new_status=new_status,
        allowed_from=allowed_from,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="상품을 찾을 수 없거나 권한이 없습니다")
    if result == "INVALID_TRANSITION":
        raise HTTPException(status_code=409, detail="현재 상태에서 해당 전이가 불가능합니다")

    return {"success": True, "sale_status": new_status}


@router.get("/my-listings/{session_id}/inquiries", tags=["seller"])
async def list_inquiries(
    session_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    repo: SessionRepository = Depends(get_session_repository),
    inquiry_repo: InquiryRepository = Depends(get_inquiry_repository),
) -> dict[str, Any]:
    """특정 상품의 문의 목록 조회. 판매자 인증 + 소유권 검증."""
    session = repo.get_by_id_and_user(session_id, user.user_id)
    if not session:
        raise HTTPException(status_code=404, detail="상품을 찾을 수 없거나 권한이 없습니다")

    inquiries = inquiry_repo.list_by_listing(session_id)
    canonical = (session.get("listing_data_jsonb") or {}).get("canonical_listing") or {}
    product_data = session.get("product_data_jsonb") or {}

    # listing 컨텍스트를 각 문의에 포함 (CTO16 요청)
    listing_context = {
        "listing_title": canonical.get("title", ""),
        "listing_price": canonical.get("price", 0),
        "thumbnail_url": (product_data.get("image_paths") or [""])[0],
    }

    return {
        "listing": listing_context,
        "inquiries": [
            {**inq, **listing_context} for inq in inquiries
        ],
        "total": len(inquiries),
    }


@router.post("/my-listings/{session_id}/inquiries/{inquiry_id}/reply", tags=["seller"])
async def reply_to_inquiry(
    session_id: str,
    inquiry_id: str,
    body: ReplyRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    repo: SessionRepository = Depends(get_session_repository),
    inquiry_repo: InquiryRepository = Depends(get_inquiry_repository),
) -> dict[str, Any]:
    """문의에 응답한다. 판매자 인증 + 소유권 검증. 상태 자동 전이 (replied + is_read)."""
    session = repo.get_by_id_and_user(session_id, user.user_id)
    if not session:
        raise HTTPException(status_code=404, detail="상품을 찾을 수 없거나 권한이 없습니다")

    inquiry = inquiry_repo.get_by_id(inquiry_id)
    if not inquiry or inquiry.get("listing_id") != session_id:
        raise HTTPException(status_code=404, detail="문의를 찾을 수 없습니다")

    updated = inquiry_repo.reply(inquiry_id, body.reply)
    if not updated:
        raise HTTPException(status_code=500, detail="응답 저장에 실패했습니다")

    logger.info("inquiry_replied listing=%s inquiry=%s", session_id, inquiry_id)
    return {"success": True, "inquiry": updated}


@router.post("/my-listings/{session_id}/inquiries/{inquiry_id}/suggest-reply", tags=["seller"])
async def suggest_inquiry_reply(
    session_id: str,
    inquiry_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    repo: SessionRepository = Depends(get_session_repository),
    inquiry_repo: InquiryRepository = Depends(get_inquiry_repository),
) -> dict[str, Any]:
    """AI가 문의 응답 초안을 제안한다. LLM 실패 시 goal별 규칙 기반 템플릿 fallback."""
    session = repo.get_by_id_and_user(session_id, user.user_id)
    if not session:
        raise HTTPException(status_code=404, detail="상품을 찾을 수 없거나 권한이 없습니다")

    inquiry = inquiry_repo.get_by_id(inquiry_id)
    if not inquiry or inquiry.get("listing_id") != session_id:
        raise HTTPException(status_code=404, detail="문의를 찾을 수 없습니다")

    listing_data = session.get("listing_data_jsonb") or {}
    canonical = listing_data.get("canonical_listing") or {}
    product_data = session.get("product_data_jsonb") or {}
    workflow_meta = session.get("workflow_meta_jsonb") or {}

    goal = workflow_meta.get("mission_goal") or session.get("strategy_goal") or "balanced"
    price = canonical.get("price", 0)
    title = canonical.get("title", "")
    message = inquiry.get("message", "")

    # 문의 유형 감지 (간단한 키워드 기반)
    msg_lower = message.lower()
    if any(kw in msg_lower for kw in ["네고", "할인", "깎", "가격", "에누리"]):
        inquiry_type = "nego"
    elif any(kw in msg_lower for kw in ["상태", "하자", "기스", "스크래치", "사용감"]):
        inquiry_type = "condition"
    else:
        inquiry_type = "default"

    # LLM 시도
    suggested_reply = None
    source = "template"
    try:
        suggested_reply = await _generate_reply_with_llm(
            message=message, title=title, price=price, goal=goal, inquiry_type=inquiry_type,
        )
        if suggested_reply:
            source = "llm"
    except Exception as e:
        logger.warning("inquiry_copilot_llm_failed session=%s error=%s", session_id, e)

    # Fallback: 규칙 기반 템플릿
    if not suggested_reply:
        from app.domain.goal_strategy import get_inquiry_reply_template
        suggested_reply = get_inquiry_reply_template(goal, inquiry_type, price)

    return {
        "suggested_reply": suggested_reply,
        "inquiry_type": inquiry_type,
        "goal": goal,
        "source": source,
    }


async def _generate_reply_with_llm(
    message: str, title: str, price: int, goal: str, inquiry_type: str,
) -> str | None:
    """LLM으로 문의 응답 초안을 생성한다."""
    try:
        import httpx
        from app.core.config import get_settings
        settings = get_settings()

        api_key = getattr(settings, "openai_api_key", None)
        if not api_key:
            return None

        from app.domain.goal_strategy import get_negotiation_policy
        nego_policy = get_negotiation_policy(goal)

        system_prompt = (
            f"당신은 중고거래 판매자의 문의 응대를 돕는 AI 비서입니다.\n"
            f"상품: {title} (가격: {price:,}원)\n"
            f"판매 전략: {goal} (협상 정책: {nego_policy})\n"
            f"구매자의 문의에 대해 친절하고 자연스러운 한국어 답변을 1~3문장으로 작성하세요.\n"
            f"반말이 아닌 존댓말을 사용하세요."
        )

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": "gpt-4.1-mini",
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": f"구매자 문의: {message}"},
                    ],
                    "max_tokens": 200,
                    "temperature": 0.7,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        logger.warning("llm_reply_generation_failed: %s", e)
        return None


@router.post("/my-listings/{session_id}/relist", tags=["seller"])
async def relist_listing(
    session_id: str,
    body: RelistRequest | None = None,
    user: AuthenticatedUser = Depends(get_current_user),
    session_service: SessionService = Depends(get_session_service),
) -> dict[str, Any]:
    """기존 상품을 재등록한다. 이미지+정보 복제 + 새 세션 생성."""
    new_price = body.new_price if body else None
    result = await session_service.relist_session(
        session_id=session_id,
        user_id=user.user_id,
        new_price=new_price,
    )
    logger.info("listing_relisted original=%s new=%s", session_id, result.get("session_id"))
    return {"success": True, "new_session": result}


# ── 헬퍼 ───────────────────────────────────────────────


def _get_category(session: dict) -> str:
    """세션에서 상품 카테고리를 추출한다."""
    product_data = session.get("product_data_jsonb") or {}
    confirmed = product_data.get("confirmed_product") or {}
    return confirmed.get("category", "")


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
        "sale_status": _get_sale_status(session),
        "category": _get_category(session),
        "created_at": session.get("created_at"),
    }


def _to_my_listing_item(session: dict) -> dict[str, Any]:
    """DB 레코드 -> 판매자 대시보드용 응답 (sale_status + inquiry 정보 포함)."""
    base = _to_market_item(session)
    base["sale_status"] = _get_sale_status(session)
    return base


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
        "sale_status": _get_sale_status(session),
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
