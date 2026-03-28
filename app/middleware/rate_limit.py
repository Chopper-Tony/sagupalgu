"""
In-memory sliding window rate limiter.

외부 의존성 없이 동작하며, 단일 프로세스 환경에서 사용.
멀티 프로세스/분산 환경에서는 Redis 기반으로 교체 필요.
"""
from __future__ import annotations

import logging
import time
from collections import defaultdict
from threading import Lock

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)

# route_group별 제한 (requests_per_minute)
_RATE_LIMITS: dict[str, int] = {
    "post:images": 5,       # 이미지 업로드
    "post:sessions": 10,    # 세션 생성
    "post:publish": 10,     # 게시 실행
    "post:rewrite": 10,     # 재작성
    "post:default": 20,     # 기타 POST
    "get:default": 60,      # 기타 GET
}

# 내부 저장소: {client_key: [timestamp, ...]}
_requests: dict[str, list[float]] = defaultdict(list)
_lock = Lock()


def _get_client_key(request: Request) -> str:
    """클라이언트 식별 키. IP 기반."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _get_route_group(method: str, path: str) -> str:
    """요청 메서드+경로를 route group으로 분류.

    같은 그룹 내 요청은 하나의 rate limit bucket을 공유한다.
    """
    if method == "POST":
        if "/images" in path:
            return "post:images"
        if path.endswith("/sessions"):
            return "post:sessions"
        if "/publish" in path:
            return "post:publish"
        if "/rewrite" in path:
            return "post:rewrite"
        return "post:default"
    return "get:default"


def _get_rate_limit(method: str, path: str) -> int:
    """요청 메서드+경로에 맞는 rate limit을 반환."""
    group = _get_route_group(method, path)
    return _RATE_LIMITS.get(group, 60)


def _is_rate_limited(client_key: str, limit: int, window: int = 60) -> tuple[bool, int]:
    """sliding window 내 요청 수를 확인한다.

    Returns:
        (is_limited, remaining)
    """
    now = time.monotonic()
    cutoff = now - window

    with _lock:
        timestamps = _requests[client_key]
        # 윈도우 밖 타임스탬프 제거
        _requests[client_key] = [ts for ts in timestamps if ts > cutoff]
        timestamps = _requests[client_key]

        if len(timestamps) >= limit:
            return True, 0

        timestamps.append(now)
        return False, limit - len(timestamps)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """요청 rate limiting 미들웨어."""

    async def dispatch(self, request: Request, call_next) -> Response:
        # health 체크는 rate limit 제외
        if request.url.path.startswith("/health"):
            return await call_next(request)

        client_key = _get_client_key(request)
        method = request.method
        path = request.url.path
        route_group = _get_route_group(method, path)
        limit = _RATE_LIMITS.get(route_group, 60)

        is_limited, remaining = _is_rate_limited(
            f"{client_key}:{route_group}", limit,
        )

        if is_limited:
            logger.warning(
                "rate_limited client=%s method=%s path=%s limit=%d",
                client_key, method, request.url.path, limit,
            )
            return JSONResponse(
                status_code=429,
                content={"detail": "요청이 너무 많습니다. 잠시 후 다시 시도해주세요."},
                headers={"Retry-After": "60"},
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        return response


def reset_rate_limiter():
    """테스트용: rate limiter 상태 초기화."""
    with _lock:
        _requests.clear()
