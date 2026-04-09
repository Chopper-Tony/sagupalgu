import asyncio
import logging
import os
import sys
from contextlib import asynccontextmanager

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


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown lifecycle — on_event deprecated 대체."""
    from app.core.config import settings
    _logger = logging.getLogger(__name__)

    # Startup: Worker 시작 (RUN_PUBLISH_WORKER=true인 프로세스에서만)
    worker = None
    if settings.run_publish_worker and settings.environment != "test":
        from app.db.publish_job_repository import PublishJobRepository
        from app.services.publish_worker import PublishWorker
        worker = PublishWorker(job_repo=PublishJobRepository())
        app.state.publish_worker = worker
        asyncio.create_task(worker.start())
        _logger.info("publish_worker_launched")

    yield

    # Shutdown: Worker graceful stop
    if worker:
        await worker.stop()
        _logger.info("publish_worker_shutdown")


def create_app() -> FastAPI:
    """App factory — 테스트·환경별 앱 생성 분리."""
    from app.api.session_router import router as session_router
    from app.core.config import settings
    from app.core.logging import configure_logging
    from app.middleware.rate_limit import RateLimitMiddleware
    from app.middleware.request_id import RequestIdMiddleware

    logger = logging.getLogger(__name__)

    configure_logging(level="DEBUG" if settings.debug else "INFO")

    application = FastAPI(
        title=settings.app_name,
        debug=settings.debug,
        lifespan=lifespan,
    )

    # CORS
    _origins = [o.strip() for o in settings.allowed_origins.split(",") if o.strip()]
    application.add_middleware(
        CORSMiddleware,
        allow_origins=_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )
    application.add_middleware(RequestIdMiddleware)
    application.add_middleware(RateLimitMiddleware)

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
        """Readiness probe — 내부 의존성 준비 상태만 확인. 외부 API ping 없음."""
        supabase_ok = False
        try:
            from app.db.client import get_supabase
            client = get_supabase()
            if client:
                client.table("sell_sessions").select("id").limit(1).execute()
                supabase_ok = True
        except Exception as e:
            logger.debug("supabase_check_failed: %s", e)
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

        # 활성 publish target: credential이 설정된 플랫폼만
        active_publishers = []
        if settings.bunjang_username:
            active_publishers.append("bunjang")
        if settings.joongna_username:
            active_publishers.append("joongna")
        if settings.daangn_device_id:
            active_publishers.append("daangn")
        publish_ok = len(active_publishers) >= 1

        # LLM provider 상세
        listing_provider = settings.listing_llm_provider
        listing_llm_ok = (
            (listing_provider == "openai" and bool(settings.openai_api_key))
            or (listing_provider == "gemini" and bool(settings.gemini_api_key))
            or (listing_provider == "solar" and bool(getattr(settings, "upstage_api_key", None)))
        )

        checks = {
            "supabase": supabase_ok,
            "vision_provider": vision_ok,
            "listing_llm": listing_llm_ok,
            "llm_fallback": has_llm,
            "publish_credentials": publish_ok,
        }
        all_ready = all(checks.values())
        return {
            "status": "ready" if all_ready else "degraded",
            "service": settings.app_name,
            "environment": settings.environment,
            "checks": checks,
            "meta": {
                "active_publishers": active_publishers,
                "vision_provider": vision_provider,
                "listing_provider": listing_provider,
            },
        }

    @application.get("/health/deep")
    def health_deep():
        """Deep check — 외부 API 연결 검증 (운영자 수동 확인용, K8s 프로브 사용 금지)."""
        llm_reachable = False
        try:
            import httpx
            if settings.openai_api_key:
                r = httpx.get(
                    "https://api.openai.com/v1/models",
                    headers={"Authorization": f"Bearer {settings.openai_api_key}"},
                    timeout=5,
                )
                llm_reachable = r.status_code == 200
            elif settings.gemini_api_key:
                r = httpx.get(
                    f"https://generativelanguage.googleapis.com/v1beta/models?key={settings.gemini_api_key}",
                    timeout=5,
                )
                llm_reachable = r.status_code == 200
        except Exception as e:
            logger.debug("llm_reachability_check_failed: %s", e)
            llm_reachable = False

        return {"llm_reachable": llm_reachable}

    @application.get("/health")
    def health():
        """하위 호환 — /health/ready와 동일."""
        return health_ready()

    # 라우터
    application.include_router(session_router, prefix=settings.api_v1_prefix)
    from app.api.platform_router import router as platform_router
    application.include_router(platform_router, prefix=settings.api_v1_prefix)
    from app.api.admin_router import router as admin_router
    application.include_router(admin_router, prefix=settings.api_v1_prefix)
    from app.api.market_router import router as market_router
    application.include_router(market_router, prefix=settings.api_v1_prefix)

    # 업로드 이미지 정적 서빙
    if os.path.isdir("uploads"):
        from fastapi.staticfiles import StaticFiles
        application.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

    return application


app = create_app()
