from fastapi import APIRouter, HTTPException

from app.repositories.session_repository import SessionRepository
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
    SessionDetailResponse,
    UploadImagesRequest,
    UploadImagesResponse,
)
from app.services.session_service import SessionService

router = APIRouter(prefix="/sessions", tags=["sessions"])

session_repository = SessionRepository()
session_service = SessionService(session_repository=session_repository)


@router.post("", response_model=CreateSessionResponse)
async def create_session():
    try:
        result = await session_service.create_session(user_id="temp-user-id")
        session_ui = await session_service.get_session(result["session_id"])
        return CreateSessionResponse(**session_ui)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{session_id}", response_model=SessionDetailResponse)
async def get_session(session_id: str):
    try:
        session_ui = await session_service.get_session(session_id)
        return SessionDetailResponse(**session_ui)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{session_id}/images", response_model=UploadImagesResponse)
async def upload_images(session_id: str, request: UploadImagesRequest):
    try:
        result = await session_service.attach_images(
            session_id=session_id,
            image_urls=request.image_urls,
        )
        return UploadImagesResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{session_id}/analyze", response_model=AnalyzeSessionResponse)
async def analyze_session(session_id: str):
    try:
        result = await session_service.analyze_session(session_id=session_id)
        return AnalyzeSessionResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{session_id}/confirm-product", response_model=ConfirmProductResponse)
async def confirm_product(session_id: str, request: ConfirmProductRequest):
    try:
        result = await session_service.confirm_product(
            session_id=session_id,
            candidate_index=request.candidate_index,
        )
        return ConfirmProductResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{session_id}/provide-product-info", response_model=ProvideProductInfoResponse)
async def provide_product_info(session_id: str, request: ProvideProductInfoRequest):
    try:
        result = await session_service.provide_product_info(
            session_id=session_id,
            model=request.model,
            brand=request.brand,
            category=request.category,
        )
        return ProvideProductInfoResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{session_id}/generate-listing", response_model=GenerateListingResponse)
async def generate_listing(session_id: str):
    try:
        result = await session_service.generate_listing(session_id=session_id)
        return GenerateListingResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{session_id}/prepare-publish", response_model=PreparePublishResponse)
async def prepare_publish(session_id: str, request: PreparePublishRequest):
    try:
        result = await session_service.prepare_publish(
            session_id=session_id,
            platform_targets=request.platform_targets,
        )
        return PreparePublishResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{session_id}/publish", response_model=PublishResponse)
async def publish_session(session_id: str):
    try:
        result = await session_service.publish_session(session_id=session_id)
        return PublishResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{session_id}/rewrite-listing")
async def rewrite_listing(session_id: str, request: dict):
    try:
        result = await session_service.rewrite_listing(
            session_id=session_id,
            instruction=request.get("instruction", ""),
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{session_id}/sale-status")
async def update_sale_status(session_id: str, request: dict):
    try:
        result = await session_service.update_sale_status(
            session_id=session_id,
            sale_status=request.get("sale_status", ""),
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))