"""
세션 API 라우터.

예외 처리는 main.py 글로벌 핸들러에 위임한다.
엔드포인트는 순수한 서비스 호출 + 응답 변환만 담당.
"""
import os
import uuid
from typing import List

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

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
