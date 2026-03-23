import asyncio
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from fastapi import FastAPI
from app.api.session_router import router as session_router
from app.core.config import settings

app = FastAPI(
    title=settings.app_name,
    debug=settings.debug,
)

@app.get("/health")
def health():
    return {"status": "ok", "service": settings.app_name}

app.include_router(session_router, prefix=settings.api_v1_prefix)