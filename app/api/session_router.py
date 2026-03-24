from fastapi import APIRouter, HTTPException

from app.domain.exceptions import (
    InvalidStateTransitionError,
    ListingGenerationError,
    ListingRewriteError,
    PublishExecutionError,
    SagupalguError,
    SessionNotFoundError,
)
from app.repositories.session_repository import SessionRepository
from app.schemas.session import (
    AnalyzeSessionResponse,
    ConfirmProductRequest,
    ConfirmProductResponse,
    CreateSessionResponse,
    ErrorResponse,
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

session_repository = SessionRepository()
session_service = SessionService(session_repository=session_repository)


def _api_error(status_code: int, error: str, message: str) -> HTTPException:
    """통일된 에러 응답 생성."""
    return HTTPException(
        status_code=status_code,
        detail=ErrorResponse(error=error, message=message).model_dump(),
    )


def _domain_error(exc: SagupalguError) -> HTTPException:
    """도메인 예외 → HTTP 코드 매핑."""
    if isinstance(exc, SessionNotFoundError):
        return _api_error(404, "session_not_found", str(exc))
    if isinstance(exc, InvalidStateTransitionError):
        return _api_error(409, "invalid_state_transition", str(exc))
    if isinstance(exc, (ListingGenerationError, ListingRewriteError)):
        return _api_error(500, "listing_error", str(exc))
    if isinstance(exc, PublishExecutionError):
        return _api_error(502, "publish_execution_error", str(exc))
    return _api_error(500, "domain_error", str(exc))


@router.post("", response_model=CreateSessionResponse)
async def create_session():
    try:
        result = await session_service.create_session(user_id="temp-user-id")
        return CreateSessionResponse(**result)
    except SagupalguError as e:
        raise _domain_error(e)
    except ValueError as e:
        raise _api_error(400, "create_session_failed", str(e))


@router.get("/{session_id}", response_model=SessionDetailResponse)
async def get_session(session_id: str):
    try:
        session_ui = await session_service.get_session(session_id)
        return SessionDetailResponse(**session_ui)
    except SagupalguError as e:
        raise _domain_error(e)
    except ValueError as e:
        raise _api_error(400, "session_not_found", str(e))


@router.post("/{session_id}/images", response_model=UploadImagesResponse)
async def upload_images(session_id: str, request: UploadImagesRequest):
    try:
        result = await session_service.attach_images(
            session_id=session_id,
            image_urls=request.image_urls,
        )
        return UploadImagesResponse(**result)
    except SagupalguError as e:
        raise _domain_error(e)
    except ValueError as e:
        raise _api_error(400, "upload_images_failed", str(e))


@router.post("/{session_id}/analyze", response_model=AnalyzeSessionResponse)
async def analyze_session(session_id: str):
    try:
        result = await session_service.analyze_session(session_id=session_id)
        return AnalyzeSessionResponse(**result)
    except SagupalguError as e:
        raise _domain_error(e)
    except ValueError as e:
        raise _api_error(400, "analyze_failed", str(e))


@router.post("/{session_id}/confirm-product", response_model=ConfirmProductResponse)
async def confirm_product(session_id: str, request: ConfirmProductRequest):
    try:
        result = await session_service.confirm_product(
            session_id=session_id,
            candidate_index=request.candidate_index,
        )
        return ConfirmProductResponse(**result)
    except SagupalguError as e:
        raise _domain_error(e)
    except ValueError as e:
        raise _api_error(400, "confirm_product_failed", str(e))


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
    except SagupalguError as e:
        raise _domain_error(e)
    except ValueError as e:
        raise _api_error(400, "provide_product_info_failed", str(e))


@router.post("/{session_id}/generate-listing", response_model=GenerateListingResponse)
async def generate_listing(session_id: str):
    try:
        result = await session_service.generate_listing(session_id=session_id)
        return GenerateListingResponse(**result)
    except SagupalguError as e:
        raise _domain_error(e)
    except ValueError as e:
        raise _api_error(400, "generate_listing_failed", str(e))


@router.post("/{session_id}/prepare-publish", response_model=PreparePublishResponse)
async def prepare_publish(session_id: str, request: PreparePublishRequest):
    try:
        result = await session_service.prepare_publish(
            session_id=session_id,
            platform_targets=request.platform_targets,
        )
        return PreparePublishResponse(**result)
    except SagupalguError as e:
        raise _domain_error(e)
    except ValueError as e:
        raise _api_error(400, "prepare_publish_failed", str(e))


@router.post("/{session_id}/publish", response_model=PublishResponse)
async def publish_session(session_id: str):
    try:
        result = await session_service.publish_session(session_id=session_id)
        return PublishResponse(**result)
    except SagupalguError as e:
        raise _domain_error(e)
    except ValueError as e:
        raise _api_error(400, "publish_failed", str(e))


@router.post("/{session_id}/rewrite-listing", response_model=RewriteListingResponse)
async def rewrite_listing(session_id: str, request: RewriteListingRequest):
    try:
        result = await session_service.rewrite_listing(
            session_id=session_id,
            instruction=request.instruction,
        )
        return RewriteListingResponse(**result)
    except SagupalguError as e:
        raise _domain_error(e)
    except ValueError as e:
        raise _api_error(400, "rewrite_listing_failed", str(e))


@router.post("/{session_id}/sale-status", response_model=SaleStatusResponse)
async def update_sale_status(session_id: str, request: SaleStatusRequest):
    try:
        result = await session_service.update_sale_status(
            session_id=session_id,
            sale_status=request.sale_status,
        )
        return SaleStatusResponse(**result)
    except SagupalguError as e:
        raise _domain_error(e)
    except ValueError as e:
        raise _api_error(400, "update_sale_status_failed", str(e))
