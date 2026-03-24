"""
세션 API 라우터.

예외 처리는 main.py 글로벌 핸들러에 위임한다.
엔드포인트는 순수한 서비스 호출 + 응답 변환만 담당.
"""
from fastapi import APIRouter, Depends

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


@router.post("/{session_id}/images", response_model=UploadImagesResponse)
async def upload_images(
    session_id: str,
    request: UploadImagesRequest,
    session_service: SessionService = Depends(get_session_service),
):
    result = await session_service.attach_images(
        session_id=session_id, image_urls=request.image_urls,
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
