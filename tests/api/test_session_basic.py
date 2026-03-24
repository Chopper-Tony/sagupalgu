"""세션 기본 API 테스트 — 헬스체크, 생성, 조회."""
import pytest

from app.domain.exceptions import InvalidStateTransitionError, SessionNotFoundError
from tests.api.conftest import BASE


class TestHealth:

    @pytest.mark.integration
    def test_health_ok(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


class TestCreateSession:

    @pytest.mark.integration
    def test_returns_200_with_session_id(self, client):
        resp = client.post(BASE)
        assert resp.status_code == 200
        data = resp.json()
        assert data["session_id"] == "sess-001"
        assert data["status"] == "created"

    @pytest.mark.integration
    def test_domain_error_maps_to_409(self, client, mock_svc):
        mock_svc.create_session.side_effect = InvalidStateTransitionError("bad transition")
        resp = client.post(BASE)
        assert resp.status_code == 409

    @pytest.mark.integration
    def test_value_error_maps_to_400(self, client, mock_svc):
        mock_svc.create_session.side_effect = ValueError("bad input")
        resp = client.post(BASE)
        assert resp.status_code == 400


class TestGetSession:

    @pytest.mark.integration
    def test_returns_session(self, client):
        resp = client.get(f"{BASE}/sess-001")
        assert resp.status_code == 200
        assert resp.json()["session_id"] == "sess-001"

    @pytest.mark.integration
    def test_not_found_maps_to_404(self, client, mock_svc):
        mock_svc.get_session.side_effect = SessionNotFoundError("not found")
        resp = client.get(f"{BASE}/missing")
        assert resp.status_code == 404

    @pytest.mark.integration
    def test_error_response_has_detail(self, client, mock_svc):
        mock_svc.get_session.side_effect = SessionNotFoundError("세션 없음")
        resp = client.get(f"{BASE}/missing")
        assert "detail" in resp.json()
