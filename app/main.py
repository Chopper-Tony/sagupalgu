import asyncio
import os
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.domain.exceptions import (
    InvalidStateTransitionError,
    InvalidUserInputError,
    ListingGenerationError,
    ListingRewriteError,
    PublishExecutionError,
    SagupalguError,
    SessionNotFoundError,
    SessionUpdateError,
)

# ── 예외 매핑 정책 (단일 진실 원천) ─────────────────────────────────
_DOMAIN_STATUS_MAP: dict[type, tuple[int, str]] = {
    SessionNotFoundError: (404, "session_not_found"),
    InvalidUserInputError: (400, "invalid_user_input"),
    InvalidStateTransitionError: (409, "invalid_state_transition"),
    SessionUpdateError: (500, "session_update_error"),
    ListingGenerationError: (500, "listing_error"),
    ListingRewriteError: (500, "listing_error"),
    PublishExecutionError: (502, "publish_execution_error"),
}


def create_app() -> FastAPI:
    """App factory — 테스트·환경별 앱 생성 분리."""
    from app.api.session_router import router as session_router
    from app.core.config import settings
    from app.core.logging import configure_logging
    from app.middleware.request_id import RequestIdMiddleware

    configure_logging(level="DEBUG" if settings.debug else "INFO")

    application = FastAPI(
        title=settings.app_name,
        debug=settings.debug,
    )

    # CORS
    _origins = [o.strip() for o in settings.allowed_origins.split(",") if o.strip()]
    application.add_middleware(
        CORSMiddleware,
        allow_origins=_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.add_middleware(RequestIdMiddleware)

    # 예외 핸들러
    @application.exception_handler(SagupalguError)
    async def sagupalgu_error_handler(request: Request, exc: SagupalguError):
        status_code, error_key = _DOMAIN_STATUS_MAP.get(type(exc), (500, "domain_error"))
        return JSONResponse(
            status_code=status_code,
            content={"detail": {"error": error_key, "message": str(exc)}},
        )

    @application.exception_handler(ValueError)
    async def value_error_handler(request: Request, exc: ValueError):
        return JSONResponse(
            status_code=400,
            content={"detail": {"error": "validation_error", "message": str(exc)}},
        )

    # Health endpoints
    @application.get("/health/live")
    def health_live():
        """Liveness probe — 프로세스 살아있음."""
        return {"status": "ok"}

    @application.get("/health/ready")
    def health_ready():
        """Readiness probe — 현재 선택된 실행 경로의 준비 상태 확인."""
        supabase_ok = False
        try:
            from app.db.client import get_supabase
            client = get_supabase()
            if client:
                client.table("sell_sessions").select("id").limit(1).execute()
                supabase_ok = True
        except Exception:
            supabase_ok = False

        vision_provider = settings.vision_provider
        vision_ok = (
            (vision_provider == "openai" and bool(settings.openai_api_key))
            or (vision_provider == "gemini" and bool(settings.gemini_api_key))
        )

        has_llm = any([
            bool(settings.openai_api_key),
            bool(settings.gemini_api_key),
            bool(getattr(settings, "upstage_api_key", None)),
        ])

        publish_targets = {"bunjang", "joongna"}
        publish_ok = any([
            "bunjang" in publish_targets and bool(settings.bunjang_username),
            "joongna" in publish_targets and bool(settings.joongna_username),
        ])

        checks = {
            "supabase": supabase_ok,
            "vision_provider": vision_ok,
            "llm_provider": has_llm,
            "publish_credentials": publish_ok,
        }
        all_ready = all(checks.values())
        return {
            "status": "ready" if all_ready else "degraded",
            "service": settings.app_name,
            "environment": settings.environment,
            "checks": checks,
        }

    @application.get("/health")
    def health():
        """하위 호환 — /health/ready와 동일."""
        return health_ready()

    # 라우터
    application.include_router(session_router, prefix=settings.api_v1_prefix)

    # 업로드 이미지 정적 서빙
    if os.path.isdir("uploads"):
        from fastapi.staticfiles import StaticFiles
        application.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

    return application


app = create_app()
