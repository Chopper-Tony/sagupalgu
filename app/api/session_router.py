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


def _resolve_next_action(status: str, needs_user_input: bool) -> str | None:
    if status == "session_created":
        return "upload_images"
    if status == "images_uploaded":
        return "analyze"
    if status == "awaiting_product_confirmation":
        return "provide_product_info" if needs_user_input else "confirm_product"
    if status == "product_confirmed":
        return "generate_listing"
    if status == "draft_generated":
        return "prepare_publish"
    if status == "awaiting_publish_approval":
        return "publish"
    if status == "publishing":
        return "poll_status"
    if status == "completed":
        return "done"
    if status in {"failed", "publishing_failed"}:
        return "retry_or_edit"
    return None


def _build_session_ui_response(session: dict) -> dict:
    product_data = session.get("product_data_jsonb", {}) or {}
    listing_data = session.get("listing_data_jsonb", {}) or {}
    workflow_meta = session.get("workflow_meta_jsonb", {}) or {}

    status = session.get("status", "")
    needs_user_input = bool(product_data.get("needs_user_input", False))

    return {
        "session_id": session["session_id"],
        "status": status,
        "checkpoint": workflow_meta.get("checkpoint"),
        "next_action": _resolve_next_action(status, needs_user_input),
        "needs_user_input": needs_user_input,
        "user_input_prompt": product_data.get("user_input_prompt"),
        "selected_platforms": session.get("selected_platforms_jsonb", []) or [],
        "product": {
            "image_paths": product_data.get("image_paths", []) or [],
            "image_count": product_data.get("image_count", 0) or 0,
            "analysis_source": product_data.get("analysis_source"),
            "candidates": product_data.get("candidates", []) or [],
            "confirmed_product": product_data.get("confirmed_product"),
        },
        "listing": {
            "market_context": listing_data.get("market_context"),
            "strategy": listing_data.get("strategy"),
            "canonical_listing": listing_data.get("canonical_listing"),
            "platform_packages": listing_data.get("platform_packages", {}) or {},
        },
        "publish": {
            "results": workflow_meta.get("publish_results", {}) or {},
        },
        "debug": {
            "graph_debug_logs": workflow_meta.get("graph_debug_logs", []) or [],
            "validation_result": workflow_meta.get("validation_result"),
            "last_error": workflow_meta.get("last_error"),
        },
    }


def _get_ui_session(session_id: str) -> dict:
    session = session_service.get_session(session_id)
    raw = session_repository.get_by_id(session_id)

    if not raw:
        raise ValueError(f"Session not found: {session_id}")

    merged = {
        **session,
        "selected_platforms_jsonb": raw.get("selected_platforms_jsonb", []) or [],
    }
    return _build_session_ui_response(merged)


@router.post("", response_model=CreateSessionResponse)
def create_session():
    user_id = "temp-user-id"
    result = session_service.create_session(user_id=user_id)
    try:
        session_ui = _get_ui_session(result["session_id"])
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return CreateSessionResponse(**session_ui)


@router.get("/{session_id}", response_model=SessionDetailResponse)
def get_session(session_id: str):
    try:
        session_ui = _get_ui_session(session_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return SessionDetailResponse(**session_ui)


@router.post("/{session_id}/images", response_model=UploadImagesResponse)
def upload_images(session_id: str, request: UploadImagesRequest):
    try:
        session_service.attach_images(
            session_id=session_id,
            image_urls=request.image_urls,
        )
        session_ui = _get_ui_session(session_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return UploadImagesResponse(**session_ui)


@router.post("/{session_id}/analyze", response_model=AnalyzeSessionResponse)
def analyze_session(session_id: str):
    try:
        session_service.analyze_session(session_id=session_id)
        session_ui = _get_ui_session(session_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return AnalyzeSessionResponse(**session_ui)


@router.post("/{session_id}/confirm-product", response_model=ConfirmProductResponse)
def confirm_product(session_id: str, request: ConfirmProductRequest):
    try:
        session_service.confirm_product(
            session_id=session_id,
            candidate_index=request.candidate_index,
        )
        session_ui = _get_ui_session(session_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return ConfirmProductResponse(**session_ui)


@router.post(
    "/{session_id}/provide-product-info",
    response_model=ProvideProductInfoResponse,
)
def provide_product_info(session_id: str, request: ProvideProductInfoRequest):
    try:
        session_service.provide_product_info(
            session_id=session_id,
            model=request.model,
            brand=request.brand,
            category=request.category,
        )
        session_ui = _get_ui_session(session_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return ProvideProductInfoResponse(**session_ui)


@router.post("/{session_id}/generate-listing", response_model=GenerateListingResponse)
def generate_listing(session_id: str):
    try:
        session_service.generate_listing(session_id=session_id)
        session_ui = _get_ui_session(session_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return GenerateListingResponse(**session_ui)


@router.post("/{session_id}/prepare-publish", response_model=PreparePublishResponse)
def prepare_publish(session_id: str, request: PreparePublishRequest):
    try:
        session_service.prepare_publish(
            session_id=session_id,
            platform_targets=request.platform_targets,
        )
        session_ui = _get_ui_session(session_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return PreparePublishResponse(**session_ui)


@router.post("/{session_id}/publish", response_model=PublishResponse)
def publish_session(session_id: str):
    try:
        session_service.publish_session(session_id=session_id)
        session_ui = _get_ui_session(session_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return PublishResponse(**session_ui)