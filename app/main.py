import asyncio
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from app.api.session_router import router as session_router
from app.core.config import settings
from app.domain.exceptions import (
    InvalidStateTransitionError,
    ListingGenerationError,
    ListingRewriteError,
    PublishExecutionError,
    SessionNotFoundError,
)

app = FastAPI(
    title=settings.app_name,
    debug=settings.debug,
)


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
    return {"status": "ok", "service": settings.app_name}

app.include_router(session_router, prefix=settings.api_v1_prefix)