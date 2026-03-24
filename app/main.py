import asyncio
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.api.session_router import router as session_router
from app.core.config import settings
from app.core.logging import configure_logging
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
from app.middleware.request_id import RequestIdMiddleware

configure_logging(level="DEBUG" if settings.debug else "INFO")

app = FastAPI(
    title=settings.app_name,
    debug=settings.debug,
)

# CORS — ALLOWED_ORIGINS 환경변수로 제어 (prod에서는 실제 도메인으로 제한)
_origins = [o.strip() for o in settings.allowed_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(RequestIdMiddleware)


# ── 예외 매핑 정책 (단일 진실 원천) ─────────────────────────────────
# SessionNotFoundError       → 404
# InvalidStateTransitionError → 409
# ListingGenerationError/ListingRewriteError → 500
# PublishExecutionError      → 502
# ValueError                 → 400

_DOMAIN_STATUS_MAP: dict[type, tuple[int, str]] = {
    SessionNotFoundError: (404, "session_not_found"),
    InvalidUserInputError: (400, "invalid_user_input"),
    InvalidStateTransitionError: (409, "invalid_state_transition"),
    SessionUpdateError: (500, "session_update_error"),
    ListingGenerationError: (500, "listing_error"),
    ListingRewriteError: (500, "listing_error"),
    PublishExecutionError: (502, "publish_execution_error"),
}


@app.exception_handler(SagupalguError)
async def sagupalgu_error_handler(request: Request, exc: SagupalguError):
    status_code, error_key = _DOMAIN_STATUS_MAP.get(type(exc), (500, "domain_error"))
    return JSONResponse(
        status_code=status_code,
        content={"detail": {"error": error_key, "message": str(exc)}},
    )


@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError):
    return JSONResponse(
        status_code=400,
        content={"detail": {"error": "validation_error", "message": str(exc)}},
    )


@app.get("/health/live")
def health_live():
    """Liveness probe — 프로세스 살아있음."""
    return {"status": "ok"}


@app.get("/health/ready")
def health_ready():
    """Readiness probe — 외부 의존성 준비 상태 확인."""
    checks = {
        "supabase_url": bool(settings.supabase_url),
        "supabase_key": bool(settings.supabase_service_role_key),
        "openai_key": bool(settings.openai_api_key),
        "gemini_key": bool(settings.gemini_api_key),
    }
    all_ready = all(checks.values())
    return {
        "status": "ready" if all_ready else "degraded",
        "service": settings.app_name,
        "environment": settings.environment,
        "checks": checks,
    }


@app.get("/health")
def health():
    """하위 호환 — /health/ready와 동일."""
    return health_ready()

app.include_router(session_router, prefix=settings.api_v1_prefix)
