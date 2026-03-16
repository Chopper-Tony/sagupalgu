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
def create_session():
    user_id = "temp-user-id"
    result = session_service.create_session(user_id=user_id)
    return CreateSessionResponse(**result)


@router.get("/{session_id}", response_model=SessionDetailResponse)
def get_session(session_id: str):
    try:
        session = session_service.get_session(session_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return SessionDetailResponse(**session)


@router.post("/{session_id}/images", response_model=UploadImagesResponse)
def upload_images(session_id: str, request: UploadImagesRequest):
    try:
        result = session_service.attach_images(
            session_id=session_id,
            image_urls=request.image_urls,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return UploadImagesResponse(**result)


@router.post("/{session_id}/analyze", response_model=AnalyzeSessionResponse)
def analyze_session(session_id: str):
    try:
        result = session_service.analyze_session(session_id=session_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return AnalyzeSessionResponse(**result)


@router.post("/{session_id}/confirm-product", response_model=ConfirmProductResponse)
def confirm_product(session_id: str, request: ConfirmProductRequest):
    try:
        result = session_service.confirm_product(
            session_id=session_id,
            candidate_index=request.candidate_index,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return ConfirmProductResponse(**result)


@router.post(
    "/{session_id}/provide-product-info",
    response_model=ProvideProductInfoResponse,
)
def provide_product_info(session_id: str, request: ProvideProductInfoRequest):
    try:
        result = session_service.provide_product_info(
            session_id=session_id,
            model=request.model,
            brand=request.brand,
            category=request.category,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return ProvideProductInfoResponse(**result)


@router.post("/{session_id}/generate-listing", response_model=GenerateListingResponse)
def generate_listing(session_id: str):
    try:
        result = session_service.generate_listing(session_id=session_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return GenerateListingResponse(**result)


@router.post("/{session_id}/prepare-publish", response_model=PreparePublishResponse)
def prepare_publish(session_id: str, request: PreparePublishRequest):
    try:
        result = session_service.prepare_publish(
            session_id=session_id,
            platform_targets=request.platform_targets,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return PreparePublishResponse(**result)


@router.post("/{session_id}/publish", response_model=PublishResponse)
def publish_session(session_id: str):
    try:
        result = session_service.publish_session(session_id=session_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return PublishResponse(**result)