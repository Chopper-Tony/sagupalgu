"""
세션 API 라우터.

예외 처리는 main.py 글로벌 핸들러에 위임한다.
엔드포인트는 순수한 서비스 호출 + 응답 변환만 담당.
"""
import os
import uuid
from typing import List

import asyncio
import json as _json

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse

from app.dependencies import get_session_service
from app.schemas.session import (
    AnalyzeSessionResponse,
    ConfirmProductRequest,
    ConfirmProductResponse,
    CreateSessionResponse,
    GenerateListingResponse,
    PreparePublishRequest,
    PreparePublishResponse,
    ProvideProductInfoRequest,
    ProvideProductInfoResponse,
    PublishResponse,
    RewriteListingRequest,
    RewriteListingResponse,
    SaleStatusRequest,
    SaleStatusResponse,
    SessionDetailResponse,
    UploadImagesRequest,
    UploadImagesResponse,
)
from app.services.session_service import SessionService

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.post("", response_model=CreateSessionResponse)
async def create_session(
    session_service: SessionService = Depends(get_session_service),
):
    result = await session_service.create_session(user_id="temp-user-id")
    return CreateSessionResponse(**result)


@router.get("/{session_id}", response_model=SessionDetailResponse)
async def get_session(
    session_id: str,
    session_service: SessionService = Depends(get_session_service),
):
    result = await session_service.get_session(session_id)
    return SessionDetailResponse(**result)


@router.get("/{session_id}/stream")
async def stream_session(
    session_id: str,
    request: Request,
    session_service: SessionService = Depends(get_session_service),
):
    """SSE 스트림으로 세션 상태 변경을 실시간 전송한다.

    폴링 대비 장점: 서버가 상태 변경 시점에만 데이터 전송 → 지연 감소, 트래픽 절약.
    클라이언트가 연결을 끊으면 자동 종료.
    """
    async def event_generator():
        last_status = None
        while True:
            if await request.is_disconnected():
                break
            try:
                result = await session_service.get_session(session_id)
                current_status = result.get("status")

                # 상태 변경 시 또는 첫 연결 시 이벤트 전송
                if current_status != last_status:
                    data = _json.dumps(result, ensure_ascii=False, default=str)
                    yield f"event: status_change\ndata: {data}\n\n"
                    last_status = current_status

                    # 폴링 불필요 상태면 마지막 전송 후 종료
                    if not _is_sse_active_status(current_status):
                        yield f"event: stream_end\ndata: {{}}\n\n"
                        break

                # 하트비트 (연결 유지)
                yield f": heartbeat\n\n"
                await asyncio.sleep(1.5)
            except Exception:
                break

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def _is_sse_active_status(status: str) -> bool:
    """SSE 스트림을 유지해야 하는 상태인지 (처리 중 상태)."""
    return status in {
        "images_uploaded",
        "market_analyzing",
        "product_confirmed",
        "publishing",
    }


_ALLOWED_MIME = {"image/jpeg", "image/png", "image/webp", "image/gif"}
_ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
_MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
_MAX_FILE_COUNT = 10


@router.post("/{session_id}/images", response_model=UploadImagesResponse)
async def upload_images(
    session_id: str,
    files: List[UploadFile] = File(..., description="업로드할 이미지 파일"),
    session_service: SessionService = Depends(get_session_service),
):
    if len(files) > _MAX_FILE_COUNT:
        raise HTTPException(status_code=422, detail=f"최대 {_MAX_FILE_COUNT}개까지 업로드 가능합니다")

    upload_dir = os.path.join("uploads", session_id)
    os.makedirs(upload_dir, exist_ok=True)

    image_urls: List[str] = []
    for f in files:
        ext = os.path.splitext(f.filename or "img.jpg")[1].lower() or ".jpg"
        if ext not in _ALLOWED_EXT:
            raise HTTPException(status_code=422, detail=f"허용되지 않는 파일 형식입니다: {ext}")
        if f.content_type and f.content_type not in _ALLOWED_MIME:
            raise HTTPException(status_code=422, detail=f"허용되지 않는 MIME 타입입니다: {f.content_type}")

        content = await f.read()
        if len(content) > _MAX_FILE_SIZE:
            raise HTTPException(status_code=422, detail=f"파일 크기가 10MB를 초과합니다: {f.filename}")

        filename = f"{uuid.uuid4().hex}{ext}"
        filepath = os.path.join(upload_dir, filename)
        with open(filepath, "wb") as fh:
            fh.write(content)
        image_urls.append(f"/uploads/{session_id}/{filename}")

    result = await session_service.attach_images(
        session_id=session_id, image_urls=image_urls,
    )
    return UploadImagesResponse(**result)


@router.post("/{session_id}/analyze", response_model=AnalyzeSessionResponse)
async def analyze_session(
    session_id: str,
    session_service: SessionService = Depends(get_session_service),
):
    result = await session_service.analyze_session(session_id=session_id)
    return AnalyzeSessionResponse(**result)


@router.post("/{session_id}/confirm-product", response_model=ConfirmProductResponse)
async def confirm_product(
    session_id: str,
    request: ConfirmProductRequest,
    session_service: SessionService = Depends(get_session_service),
):
    result = await session_service.confirm_product(
        session_id=session_id, candidate_index=request.candidate_index,
    )
    return ConfirmProductResponse(**result)


@router.post("/{session_id}/provide-product-info", response_model=ProvideProductInfoResponse)
async def provide_product_info(
    session_id: str,
    request: ProvideProductInfoRequest,
    session_service: SessionService = Depends(get_session_service),
):
    result = await session_service.provide_product_info(
        session_id=session_id, model=request.model,
        brand=request.brand, category=request.category,
    )
    return ProvideProductInfoResponse(**result)


@router.post("/{session_id}/generate-listing", response_model=GenerateListingResponse)
async def generate_listing(
    session_id: str,
    session_service: SessionService = Depends(get_session_service),
):
    result = await session_service.generate_listing(session_id=session_id)
    return GenerateListingResponse(**result)


@router.post("/{session_id}/prepare-publish", response_model=PreparePublishResponse)
async def prepare_publish(
    session_id: str,
    request: PreparePublishRequest,
    session_service: SessionService = Depends(get_session_service),
):
    result = await session_service.prepare_publish(
        session_id=session_id, platform_targets=request.platform_targets,
    )
    return PreparePublishResponse(**result)


@router.post("/{session_id}/publish", response_model=PublishResponse)
async def publish_session(
    session_id: str,
    session_service: SessionService = Depends(get_session_service),
):
    result = await session_service.publish_session(session_id=session_id)
    return PublishResponse(**result)


@router.post("/{session_id}/rewrite-listing", response_model=RewriteListingResponse)
async def rewrite_listing(
    session_id: str,
    request: RewriteListingRequest,
    session_service: SessionService = Depends(get_session_service),
):
    result = await session_service.rewrite_listing(
        session_id=session_id, instruction=request.instruction,
    )
    return RewriteListingResponse(**result)


@router.post("/{session_id}/seller-tips")
async def get_seller_tips(
    session_id: str,
    session_service: SessionService = Depends(get_session_service),
):
    """판매 팁 생성 — AI가 현재 판매글을 분석하여 가격·사진·제목 개선 팁을 제공한다."""
    session = await session_service.get_session(session_id)
    listing = session.get("canonical_listing") or {}
    market = session.get("market_context") or {}
    trace = session.get("agent_trace") or {}

    tips = []
    price = listing.get("price", 0)
    median = market.get("median_price", 0)

    # 가격 적절성 피드백
    if median > 0 and price > 0:
        ratio = price / median
        if ratio > 1.1:
            tips.append({
                "category": "price",
                "message": f"현재 가격({price:,}원)이 시세 중앙값({median:,}원)보다 {int((ratio-1)*100)}% 높습니다. 가격을 낮추면 판매 속도가 빨라질 수 있습니다.",
                "priority": "high",
            })
        elif ratio < 0.85:
            tips.append({
                "category": "price",
                "message": f"현재 가격({price:,}원)이 시세 대비 매우 저렴합니다. 가격을 올려도 충분히 팔릴 수 있습니다.",
                "priority": "medium",
            })
        else:
            tips.append({
                "category": "price",
                "message": f"가격({price:,}원)이 시세({median:,}원) 대비 적절합니다.",
                "priority": "low",
            })

    # 사진 가이드
    images = listing.get("images") or []
    if len(images) < 3:
        tips.append({
            "category": "photo",
            "message": "사진을 3장 이상 올리면 구매자 신뢰도가 크게 높아집니다. 정면·후면·측면 각도를 추천합니다.",
            "priority": "high",
        })

    # 제목 길이
    title = listing.get("title", "")
    if len(title) < 15:
        tips.append({
            "category": "title",
            "message": "제목이 짧습니다. 브랜드·모델·상태·용량 등 키워드를 추가하면 검색 노출이 늘어납니다.",
            "priority": "medium",
        })

    # Critic 점수 기반 팁
    critic_score = trace.get("critic_score")
    if critic_score and critic_score < 80:
        tips.append({
            "category": "quality",
            "message": f"AI 품질 평가 {critic_score}점입니다. '수정 요청'으로 설명을 보완하면 점수가 올라갑니다.",
            "priority": "medium",
        })

    return {"session_id": session.get("session_id"), "tips": tips}


@router.post("/{session_id}/buyer-analysis")
async def buyer_price_analysis(
    session_id: str,
    session_service: SessionService = Depends(get_session_service),
):
    """구매자 관점 가격 분석 — 이 가격이 적정한지, 협상 여지가 있는지 AI가 분석한다."""
    session = await session_service.get_session(session_id)
    listing = session.get("canonical_listing") or {}
    market = session.get("market_context") or {}

    price = listing.get("price", 0)
    median = market.get("median_price", 0)
    price_band = market.get("price_band") or []
    low = price_band[0] if len(price_band) >= 2 else 0
    high = price_band[1] if len(price_band) >= 2 else 0

    analysis = {
        "price": price,
        "market_median": median,
        "price_band": {"low": low, "high": high},
        "verdict": "unknown",
        "negotiation_room": 0,
        "recommendations": [],
    }

    if median > 0 and price > 0:
        ratio = price / median
        if ratio > 1.15:
            analysis["verdict"] = "overpriced"
            analysis["negotiation_room"] = int(price - median)
            analysis["recommendations"] = [
                f"시세({median:,}원) 대비 {int((ratio-1)*100)}% 비쌉니다",
                f"{median:,}원 근처로 네고 시도를 추천합니다",
                "비슷한 조건의 다른 매물도 비교해보세요",
            ]
        elif ratio > 1.0:
            analysis["verdict"] = "slightly_high"
            analysis["negotiation_room"] = int(price - median)
            analysis["recommendations"] = [
                f"시세보다 약간 높지만 상태가 좋다면 합리적입니다",
                f"5~10% 정도 네고 여지가 있을 수 있습니다",
            ]
        elif ratio > 0.85:
            analysis["verdict"] = "fair"
            analysis["recommendations"] = [
                "시세 대비 적정 가격입니다",
                "상태·구성품을 꼼꼼히 확인 후 구매하세요",
            ]
        else:
            analysis["verdict"] = "good_deal"
            analysis["recommendations"] = [
                f"시세({median:,}원)보다 {int((1-ratio)*100)}% 저렴합니다",
                "빠르게 결정하는 것을 추천합니다",
                "너무 싸면 상태를 꼼꼼히 확인하세요",
            ]

    return {"session_id": session.get("session_id"), "analysis": analysis}


@router.post("/{session_id}/sale-status", response_model=SaleStatusResponse)
async def update_sale_status(
    session_id: str,
    request: SaleStatusRequest,
    session_service: SessionService = Depends(get_session_service),
):
    result = await session_service.update_sale_status(
        session_id=session_id, sale_status=request.sale_status,
    )
    return SaleStatusResponse(**result)
