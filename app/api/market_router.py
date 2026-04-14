"""마켓 API — 공개 상품 조회 + 판매자 상품 관리."""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
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
    sort: str | None = Query(default=None, description="정렬 (price_asc/price_desc/latest)"),
    repo: SessionRepository = Depends(get_session_repository),
) -> dict[str, Any]:
    """completed 상태 세션의 상품 목록을 반환한다. 검색/가격/판매상태/카테고리/정렬 지원."""
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

    # 정렬
    if sort == "price_asc":
        items.sort(key=lambda r: _get_price(r))
    elif sort == "price_desc":
        items.sort(key=lambda r: _get_price(r), reverse=True)
    # latest는 기본 (created_at desc — DB에서 이미 정렬됨)

    return {
        "items": [_to_market_item(row) for row in items],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


# ── 구매 문의 ─────────────────────��───────────────────


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

    # 알림 (보조 — 실패해도 OK)
    discord_sent = await _send_inquiry_discord(
        session_id=session_id,
        product_title=title,
        name=body.name,
        contact=body.contact,
        message=body.message,
    )
    email_sent = await _send_inquiry_email(
        session_id=session_id,
        product_title=title,
        name=body.name,
        contact=body.contact,
        message=body.message,
    )

    return {"success": True, "inquiry_id": inquiry.get("id"), "discord_sent": discord_sent, "email_sent": email_sent}


# ── 구매자용 AI 상품 챗봇 ──────────────────────────────


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=500)


@router.post("/{session_id}/chat")
async def chat_with_product(
    session_id: str,
    body: ChatRequest,
    repo: SessionRepository = Depends(get_session_repository),
) -> dict[str, Any]:
    """구매자가 상품에 대해 AI에게 질문한다. 상품 정보 + LLM 지식 기반 답변."""
    row = repo.get_completed_by_id(session_id)
    if not row:
        raise HTTPException(status_code=404, detail="상품을 찾을 수 없습니다.")

    listing_data = row.get("listing_data_jsonb") or {}
    canonical = listing_data.get("canonical_listing") or {}
    product_data = row.get("product_data_jsonb") or {}
    confirmed = product_data.get("confirmed_product") or {}
    workflow_meta = row.get("workflow_meta_jsonb") or {}
    market_context = workflow_meta.get("market_context") or {}

    reply = await _generate_chat_reply(
        message=body.message,
        title=canonical.get("title", ""),
        description=canonical.get("description", ""),
        price=canonical.get("price", 0),
        tags=canonical.get("tags") or [],
        brand=confirmed.get("brand", ""),
        model=confirmed.get("model", ""),
        category=confirmed.get("category", ""),
        confidence=confirmed.get("confidence", 0),
        median_price=market_context.get("median_price"),
        price_band=market_context.get("price_band") or [],
        sample_count=market_context.get("sample_count", 0),
        sale_status=_get_sale_status(row),
    )

    if not reply:
        reply = "현재 AI 상담이 불가합니다. 판매자에게 직접 문의해주세요."

    return {"reply": reply, "source": "llm" if reply != "현재 AI 상담이 불가합니다. 판매자에게 직접 문의해주세요." else "fallback"}


async def _generate_chat_reply(
    message: str,
    title: str,
    description: str,
    price: int,
    tags: list[str],
    brand: str,
    model: str,
    category: str,
    confidence: float,
    median_price: int | None,
    price_band: list,
    sample_count: int,
    sale_status: str,
) -> str | None:
    """상품 정보 기반 구매자 질문 AI 답변."""
    try:
        import httpx
        from app.core.config import get_settings
        settings = get_settings()

        api_key = getattr(settings, "openai_api_key", None)
        if not api_key:
            return None

        market_info = ""
        if median_price:
            market_info = f"\n시세 중앙값: {median_price:,}원\n가격대: {price_band}\n표본: {sample_count}건"

        system_prompt = (
            f"너는 중고거래 상품 상담 AI입니다.\n"
            f"아래 상품 정보를 기반으로 구매자의 질문에 친절하게 답변하세요.\n"
            f"상품 정보에 없는 내용 중 제품 일반 스펙(용량, eSIM, 크기, 출시일 등)은 네가 아는 지식으로 보충하세요.\n"
            f"판매자 개별 상태(흠집, 배터리 수명 등)는 정보 없으면 '판매자에게 직접 문의해주세요'로 안내하세요.\n"
            f"한국어 존댓말로 1~4문장 이내로 답변하세요.\n\n"
            f"[판매글 정보]\n"
            f"상품명: {title}\n"
            f"가격: {price:,}원\n"
            f"설명: {description[:500]}\n"
            f"태그: {', '.join(tags[:5])}\n\n"
            f"[AI 분석 결과]\n"
            f"브랜드: {brand}\n"
            f"모델: {model}\n"
            f"카테고리: {category}\n"
            f"AI 확신도: {confidence}\n"
            f"{market_info}\n"
            f"판매 상태: {sale_status}"
        )

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": "gpt-4.1-mini",
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": message},
                    ],
                    "max_tokens": 300,
                    "temperature": 0.7,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        logger.warning("product_chat_llm_failed: %s", e)
        return None


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
    """내 상품 목록 (판매자 대시보드용). inquiry_count + copilot_suggestions + publish_results 포함."""
    items = repo.list_by_user(user.user_id, sale_status_filter=sale_status_filter)
    result = []
    for row in items:
        item = _to_my_listing_item(row)
        sid = row.get("id", "")
        item["inquiry_count"] = inquiry_repo.count_by_listing(sid)
        item["unread_inquiry_count"] = inquiry_repo.count_unread(sid)
        item["copilot_suggestions"] = _compute_copilot_suggestions(row, item["inquiry_count"])
        item["publish_results"] = _extract_publish_results(row)
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
    # InvalidStateTransitionError는 main.py 글로벌 핸들러에서 409로 변환

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


@router.post("/my-listings/{session_id}/mock-inquiry", tags=["seller"])
async def create_mock_inquiry(
    session_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    repo: SessionRepository = Depends(get_session_repository),
    inquiry_repo: InquiryRepository = Depends(get_inquiry_repository),
) -> dict[str, Any]:
    """테스트 문의 생성 (dev 환경 전용). prod에서는 404."""
    from app.core.config import get_settings
    settings = get_settings()
    if settings.environment not in ("local", "dev"):
        raise HTTPException(status_code=404)

    session = repo.get_by_id_and_user(session_id, user.user_id)
    if not session:
        raise HTTPException(status_code=404, detail="상품을 찾을 수 없거나 권한이 없습니다")

    import random
    names = ["김구매", "이관심", "박문의", "최테스트", "정사용자"]
    messages = [
        "네고 가능하세요?",
        "상태 어떤가요? 하자 있나요?",
        "직거래 가능하세요? 서울 강남역 근처입니다.",
        "택배 거래 가능한가요? 택배비 포함인가요?",
        "아직 판매 중인가요? 바로 구매하고 싶습니다.",
    ]
    name = random.choice(names)
    inquiry = inquiry_repo.create(
        listing_id=session_id,
        buyer_name=name,
        buyer_contact=f"010-{random.randint(1000,9999)}-{random.randint(1000,9999)}",
        message=random.choice(messages),
    )
    return {"success": True, "inquiry": inquiry}


@router.get("/sellers/{user_id}/profile", tags=["market"])
async def get_seller_profile(
    user_id: str,
    repo: SessionRepository = Depends(get_session_repository),
) -> dict[str, Any]:
    """판매자 프로필 (공개). 등록 상품 수 + 판매 완료 수."""
    all_items = repo.list_by_user(user_id)
    total_listings = len(all_items)
    sold_count = sum(1 for item in all_items if _get_sale_status(item) == "sold")
    return {
        "user_id": user_id,
        "nickname": f"판매자 {user_id[:8]}",
        "total_listings": total_listings,
        "sold_count": sold_count,
    }


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


# ── 상세 (/{session_id} — 반드시 고정 경로 라우트 뒤에 배치) ──


@router.get("/{session_id}")
async def get_market_item(
    session_id: str,
    repo: SessionRepository = Depends(get_session_repository),
) -> dict[str, Any]:
    """completed 상태 세션의 상품 상세 정보를 반환한다. view_count 증가."""
    row = repo.get_completed_by_id(session_id)
    if not row:
        raise HTTPException(status_code=404, detail="상품을 찾을 수 ���습니다.")
    try:
        listing_data = dict(row.get("listing_data_jsonb") or {})
        listing_data["view_count"] = (listing_data.get("view_count") or 0) + 1
        repo.update(session_id, {"listing_data_jsonb": listing_data})
    except Exception:
        pass
    return _to_market_detail(row)


# ── 헬퍼 ───────���───────────────────────────────────────


def _compute_copilot_suggestions(session: dict, inquiry_count: int) -> list[dict[str, str]]:
    """등록 경과일 + 문의 수 기반 가격/제목/재등록 제안을 계산한다."""
    suggestions: list[dict[str, str]] = []
    sale_status = _get_sale_status(session)
    if sale_status != "available":
        return suggestions

    created_at = session.get("created_at")
    if not created_at:
        return suggestions

    try:
        if isinstance(created_at, str):
            created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        else:
            created = created_at
        days_listed = (datetime.now(timezone.utc) - created).days
    except (ValueError, TypeError):
        return suggestions

    listing_data = session.get("listing_data_jsonb") or {}
    canonical = listing_data.get("canonical_listing") or {}
    price = canonical.get("price", 0)

    if days_listed >= 3 and inquiry_count == 0:
        suggested_price = int(price * 0.95) if price > 0 else 0
        suggestions.append({
            "type": "price",
            "message": f"등록 {days_listed}일 경과, 문의 0건. 가격을 {suggested_price:,}원으로 낮추면 문의 확률이 올라가요.",
            "urgency": "low" if days_listed < 7 else "medium",
        })

    if days_listed >= 7 and inquiry_count == 0:
        suggestions.append({
            "type": "title",
            "message": "제목에 [급처] 또는 [가격인하] 키워드를 추가해보세요.",
            "urgency": "medium",
        })

    if days_listed >= 14:
        suggestions.append({
            "type": "relist",
            "message": "재등록하면 새 글로 상위 노출돼요. 재등록을 추천합니다.",
            "urgency": "high",
        })

    return suggestions


def _extract_publish_results(session: dict) -> list[dict[str, Any]]:
    """세션의 외부 플랫폼 게시 결과를 추출한다."""
    workflow_meta = session.get("workflow_meta_jsonb") or {}
    publish_results = workflow_meta.get("publish_results") or {}
    results = []
    platform_label = {"bunjang": "번개장터", "joongna": "중고나라", "daangn": "당근마켓"}
    for platform, detail in publish_results.items():
        if not isinstance(detail, dict):
            continue
        results.append({
            "platform": platform,
            "platform_name": platform_label.get(platform, platform),
            "success": detail.get("success", False),
            "external_url": detail.get("external_url") or detail.get("listing_url") or "",
        })
    return results


def _get_price(session: dict) -> int:
    """세션에서 가격을 추출한다."""
    listing_data = session.get("listing_data_jsonb") or {}
    canonical = listing_data.get("canonical_listing") or {}
    price = canonical.get("price", 0)
    try:
        return int(price)
    except (ValueError, TypeError):
        return 0


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
    """DB 레코드 -> 판매자 대시보드용 응답 (sale_status + 성과 요약 포함)."""
    base = _to_market_item(session)
    base["sale_status"] = _get_sale_status(session)

    # 성과 요약 (SC-1)
    listing_data = session.get("listing_data_jsonb") or {}
    base["view_count"] = listing_data.get("view_count", 0)

    # 시세 대비 위치
    workflow_meta = session.get("workflow_meta_jsonb") or {}
    market_context = workflow_meta.get("market_context") or {}
    median_price = market_context.get("median_price")
    current_price = base.get("price", 0)
    if median_price and current_price and median_price > 0:
        diff_pct = round((current_price - median_price) / median_price * 100)
        if diff_pct > 0:
            base["market_position"] = f"시세 대비 {diff_pct}% 높음"
        elif diff_pct < 0:
            base["market_position"] = f"시세 대비 {abs(diff_pct)}% 낮음"
        else:
            base["market_position"] = "시세 적정가"
    else:
        base["market_position"] = None

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
        "seller_id": session.get("user_id"),
        "view_count": listing_data.get("view_count", 0),
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


async def _send_inquiry_email(
    session_id: str,
    product_title: str,
    name: str,
    contact: str,
    message: str,
) -> bool:
    """판매자에게 구매 문의 이메일 알림을 전송한다."""
    try:
        import smtplib
        from email.mime.text import MIMEText

        smtp_email = os.getenv("SMTP_EMAIL")
        smtp_password = os.getenv("SMTP_APP_PASSWORD")
        if not smtp_email or not smtp_password:
            logger.info("SMTP 미설정, 이메일 알림 생략 session=%s", session_id)
            return False

        subject = f"[사구팔구] 구매 문의 - {product_title}"
        body = (
            f"상품: {product_title}\n"
            f"세션: {session_id}\n"
            f"─────────────────────\n"
            f"문의자: {name}\n"
            f"연락처: {contact}\n"
            f"─────────────────────\n"
            f"메시지:\n{message}\n"
        )

        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = subject
        msg["From"] = smtp_email
        msg["To"] = smtp_email  # 판매자 본인에게 전송

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(smtp_email, smtp_password)
            server.send_message(msg)

        logger.info("inquiry_email_sent session=%s name=%s", session_id, name)
        return True

    except Exception as e:
        logger.warning("inquiry_email_failed session=%s error=%s", session_id, e, exc_info=True)
        return False
