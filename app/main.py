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
    ListingGenerationError,
    ListingRewriteError,
    PublishExecutionError,
    SessionNotFoundError,
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


@app.exception_handler(SessionNotFoundError)
async def session_not_found_handler(request: Request, exc: SessionNotFoundError):
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(InvalidStateTransitionError)
async def invalid_transition_handler(request: Request, exc: InvalidStateTransitionError):
    return JSONResponse(status_code=409, content={"detail": str(exc)})


@app.exception_handler(ListingGenerationError)
async def listing_generation_handler(request: Request, exc: ListingGenerationError):
    return JSONResponse(status_code=500, content={"detail": str(exc)})


@app.exception_handler(ListingRewriteError)
async def listing_rewrite_handler(request: Request, exc: ListingRewriteError):
    return JSONResponse(status_code=500, content={"detail": str(exc)})


@app.exception_handler(PublishExecutionError)
async def publish_execution_handler(request: Request, exc: PublishExecutionError):
    return JSONResponse(status_code=502, content={"detail": str(exc)})


@app.get("/health")
def health():
    checks = {
        "supabase_url": bool(settings.supabase_url),
        "openai_key": bool(settings.openai_api_key),
        "gemini_key": bool(settings.gemini_api_key),
    }
    return {
        "status": "ok",
        "service": settings.app_name,
        "environment": settings.environment,
        "checks": checks,
    }

app.include_router(session_router, prefix=settings.api_v1_prefix)