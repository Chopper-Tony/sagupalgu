"""
관찰 가능성(Observability) 테스트

- JsonFormatter: JSON 출력 필드 검증
- get/set/reset_request_id: contextvars 동작 검증
- RequestIdMiddleware: X-Request-ID 헤더 전파 검증
- /health 상세 응답 검증
"""
import json
import logging
import uuid
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.core.logging import (
    JsonFormatter,
    get_request_id,
    reset_request_id,
    set_request_id,
)
from app.dependencies import get_session_service
from app.main import app


# ─────────────────────────────────────────────────────────────────
# JsonFormatter
# ─────────────────────────────────────────────────────────────────

class TestJsonFormatter:

    def _make_record(self, msg: str, level=logging.INFO, **extra) -> logging.LogRecord:
        record = logging.LogRecord(
            name="test", level=level,
            pathname="", lineno=0,
            msg=msg, args=(), exc_info=None,
        )
        for k, v in extra.items():
            setattr(record, k, v)
        return record

    @pytest.mark.unit
    def test_output_is_valid_json(self):
        fmt = JsonFormatter()
        record = self._make_record("hello")
        result = fmt.format(record)
        parsed = json.loads(result)
        assert isinstance(parsed, dict)

    @pytest.mark.unit
    def test_required_fields_present(self):
        fmt = JsonFormatter()
        record = self._make_record("test message")
        parsed = json.loads(fmt.format(record))
        assert "timestamp" in parsed
        assert "level" in parsed
        assert "logger" in parsed
        assert "message" in parsed

    @pytest.mark.unit
    def test_message_content(self):
        fmt = JsonFormatter()
        record = self._make_record("안녕하세요")
        parsed = json.loads(fmt.format(record))
        assert parsed["message"] == "안녕하세요"

    @pytest.mark.unit
    def test_extra_session_id_included(self):
        fmt = JsonFormatter()
        record = self._make_record("msg", session_id="sess-001")
        parsed = json.loads(fmt.format(record))
        assert parsed["session_id"] == "sess-001"

    @pytest.mark.unit
    def test_request_id_from_contextvars(self):
        fmt = JsonFormatter()
        token = set_request_id("req-xyz")
        try:
            record = self._make_record("msg")
            parsed = json.loads(fmt.format(record))
            assert parsed["request_id"] == "req-xyz"
        finally:
            reset_request_id(token)

    @pytest.mark.unit
    def test_no_request_id_when_context_empty(self):
        fmt = JsonFormatter()
        # 컨텍스트가 비어 있으면 request_id 필드 없음
        token = set_request_id("")
        try:
            record = self._make_record("msg")
            parsed = json.loads(fmt.format(record))
            assert "request_id" not in parsed
        finally:
            reset_request_id(token)

    @pytest.mark.unit
    def test_level_name_in_output(self):
        fmt = JsonFormatter()
        record = self._make_record("err", level=logging.ERROR)
        parsed = json.loads(fmt.format(record))
        assert parsed["level"] == "ERROR"


# ─────────────────────────────────────────────────────────────────
# contextvars helpers
# ─────────────────────────────────────────────────────────────────

class TestRequestIdContextVars:

    @pytest.mark.unit
    def test_default_is_empty(self):
        token = set_request_id("")
        try:
            assert get_request_id() == ""
        finally:
            reset_request_id(token)

    @pytest.mark.unit
    def test_set_and_get(self):
        token = set_request_id("abc-123")
        try:
            assert get_request_id() == "abc-123"
        finally:
            reset_request_id(token)

    @pytest.mark.unit
    def test_reset_restores_previous(self):
        outer = set_request_id("outer")
        inner = set_request_id("inner")
        assert get_request_id() == "inner"
        reset_request_id(inner)
        assert get_request_id() == "outer"
        reset_request_id(outer)


# ─────────────────────────────────────────────────────────────────
# RequestIdMiddleware (TestClient)
# ─────────────────────────────────────────────────────────────────

@pytest.fixture
def api_client():
    mock_svc = MagicMock()
    app.dependency_overrides[get_session_service] = lambda: mock_svc
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


class TestRequestIdMiddleware:

    @pytest.mark.integration
    def test_response_contains_x_request_id(self, api_client):
        resp = api_client.get("/health")
        assert "x-request-id" in resp.headers

    @pytest.mark.integration
    def test_custom_request_id_echoed(self, api_client):
        custom_id = "my-trace-id-001"
        resp = api_client.get("/health", headers={"X-Request-ID": custom_id})
        assert resp.headers["x-request-id"] == custom_id

    @pytest.mark.integration
    def test_auto_generated_id_is_uuid(self, api_client):
        resp = api_client.get("/health")
        rid = resp.headers["x-request-id"]
        parsed = uuid.UUID(rid)  # 유효한 UUID 형식이면 예외 없음
        assert str(parsed) == rid

    @pytest.mark.integration
    def test_different_requests_get_different_ids(self, api_client):
        rid1 = api_client.get("/health").headers["x-request-id"]
        rid2 = api_client.get("/health").headers["x-request-id"]
        assert rid1 != rid2


# ─────────────────────────────────────────────────────────────────
# /health 상세 응답
# ─────────────────────────────────────────────────────────────────

class TestHealthEndpoint:

    @pytest.mark.integration
    def test_status_ok(self, api_client):
        resp = api_client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    @pytest.mark.integration
    def test_service_name_present(self, api_client):
        resp = api_client.get("/health")
        assert "service" in resp.json()

    @pytest.mark.integration
    def test_environment_field_present(self, api_client):
        resp = api_client.get("/health")
        assert "environment" in resp.json()

    @pytest.mark.integration
    def test_checks_field_present(self, api_client):
        resp = api_client.get("/health")
        data = resp.json()
        assert "checks" in data
        checks = data["checks"]
        assert "supabase_url" in checks
        assert "openai_key" in checks
        assert "gemini_key" in checks

    @pytest.mark.integration
    def test_checks_are_booleans(self, api_client):
        resp = api_client.get("/health")
        checks = resp.json()["checks"]
        for val in checks.values():
            assert isinstance(val, bool)
