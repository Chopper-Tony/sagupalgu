"""
app/core/logging.py — 구조화 JSON 로깅 설정.

표준 라이브러리 logging만 사용 (신규 의존성 없음).
모든 로그가 JSON 한 줄로 출력되어 CloudWatch / 로그 수집기에서 파싱 가능.
request_id가 contextvars에 설정돼 있으면 자동으로 포함된다.
"""
from __future__ import annotations

import json
import logging
import sys
from contextvars import ContextVar
from datetime import datetime, timezone

# RequestIdMiddleware가 설정한 request_id를 로그에 자동 포함
_REQUEST_ID_CTX: ContextVar[str] = ContextVar("request_id", default="")


def get_request_id() -> str:
    return _REQUEST_ID_CTX.get()


def set_request_id(value: str) -> object:
    return _REQUEST_ID_CTX.set(value)


def reset_request_id(token: object) -> None:
    _REQUEST_ID_CTX.reset(token)


class JsonFormatter(logging.Formatter):
    """log record를 JSON 한 줄로 직렬화하는 포맷터."""

    EXTRA_FIELDS = ("request_id", "session_id", "status", "latency_ms", "platform")

    def format(self, record: logging.LogRecord) -> str:
        log_obj: dict = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # contextvars request_id 자동 포함
        ctx_rid = get_request_id()
        if ctx_rid:
            log_obj["request_id"] = ctx_rid

        # LogRecord에 직접 심어진 추가 필드
        for field in self.EXTRA_FIELDS:
            if hasattr(record, field) and field != "request_id":
                log_obj[field] = getattr(record, field)

        if record.exc_info:
            log_obj["exc_info"] = self.formatException(record.exc_info)

        return json.dumps(log_obj, ensure_ascii=False)


def configure_logging(level: str = "INFO") -> None:
    """애플리케이션 시작 시 1회 호출. 모든 로거를 JSON 포맷으로 통일."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())

    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    root.handlers.clear()
    root.addHandler(handler)

    # uvicorn 내장 로거도 동일 포맷으로 통합
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        lgr = logging.getLogger(name)
        lgr.handlers.clear()
        lgr.propagate = True

    # Supabase/HTTP 클라이언트의 과도한 DEBUG 로그 억제
    for noisy in ("hpack", "httpcore", "httpx", "h2", "h11"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
