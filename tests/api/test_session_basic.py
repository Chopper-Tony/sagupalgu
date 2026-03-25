"""세션 기본 API 테스트 — 헬스체크, 생성, 조회."""
import pytest

from app.domain.exceptions import InvalidStateTransitionError, SessionNotFoundError
from tests.api.conftest import BASE


class TestHealth:

    @pytest.mark.integration
    def test_health_ok(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] in ("ready", "degraded")

    @pytest.mark.integration
    def test_health_live(self, client):
        resp = client.get("/health/live")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    @pytest.mark.integration
    def test_health_ready_has_checks(self, client):
        resp = client.get("/health/ready")
        assert resp.status_code == 200
        data = resp.json()
        assert "checks" in data
        assert "supabase" in data["checks"]
        assert "vision_provider" in data["checks"]
        assert "listing_llm" in data["checks"]
        assert "publish_credentials" in data["checks"]
        assert "active_publishers" in data.get("meta", {})


class TestCreateSession:

    @pytest.mark.integration
    def test_returns_200_with_session_id(self, client):
        resp = client.post(BASE)
        assert resp.status_code == 200
        data = resp.json()
        assert data["session_id"] == "sess-001"
        assert data["status"] == "session_created"

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


class TestResponseShape:
    """프론트엔드 SessionResponse 계약과 백엔드 응답 shape 일치 검증."""

    FRONTEND_REQUIRED_FIELDS = {
        "session_id", "status", "next_action", "needs_user_input",
        "clarification_prompt", "product_candidates", "confirmed_product",
        "canonical_listing", "market_context", "platform_results",
        "optimization_suggestion", "rewrite_instruction", "last_error",
        "image_urls", "selected_platforms",
    }

    @pytest.mark.integration
    def test_create_session_has_all_frontend_fields(self, client):
        data = client.post(BASE).json()
        missing = self.FRONTEND_REQUIRED_FIELDS - set(data.keys())
        assert missing == set(), f"응답에 프론트엔드 필수 필드 누락: {missing}"

    @pytest.mark.integration
    def test_get_session_has_all_frontend_fields(self, client):
        data = client.get(f"{BASE}/sess-001").json()
        missing = self.FRONTEND_REQUIRED_FIELDS - set(data.keys())
        assert missing == set(), f"응답에 프론트엔드 필수 필드 누락: {missing}"

    @pytest.mark.integration
    def test_flat_fields_types(self, client):
        data = client.get(f"{BASE}/sess-001").json()
        assert isinstance(data["image_urls"], list)
        assert isinstance(data["product_candidates"], list)
        assert isinstance(data["platform_results"], list)
        assert isinstance(data["selected_platforms"], list)
