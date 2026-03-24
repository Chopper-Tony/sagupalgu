"""
app/middleware/request_id.py — X-Request-ID 미들웨어.

요청마다 고유 ID를 부여하고 contextvars에 저장한다.
- 클라이언트가 X-Request-ID 헤더를 보내면 그대로 사용 (트레이싱 연속성)
- 없으면 UUID4 신규 발급
- 응답 헤더에 X-Request-ID를 포함해 클라이언트가 추적 가능하도록 함
- app/core/logging.py의 get_request_id()로 모든 로그에 자동 포함됨
"""
from __future__ import annotations

import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.logging import reset_request_id, set_request_id


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        token = set_request_id(request_id)
        try:
            response = await call_next(request)
        finally:
            reset_request_id(token)
        response.headers["X-Request-ID"] = request_id
        return response
