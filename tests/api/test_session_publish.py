"""세션 게시·판매 API 테스트 — 게시 준비, 게시, 판매 상태."""
import pytest

from app.domain.exceptions import (
    InvalidStateTransitionError,
    PublishExecutionError,
    SessionNotFoundError,
)
from tests.api.conftest import BASE


class TestPreparePublish:

    @pytest.mark.integration
    def test_returns_awaiting_approval(self, client):
        resp = client.post(
            f"{BASE}/sess-001/prepare-publish",
            json={"platform_targets": ["bunjang", "joongna"]},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "awaiting_publish_approval"

    @pytest.mark.integration
    def test_missing_platform_targets_returns_422(self, client):
        resp = client.post(f"{BASE}/sess-001/prepare-publish", json={})
        assert resp.status_code == 422

    @pytest.mark.integration
    def test_value_error_maps_to_400(self, client, mock_svc):
        mock_svc.prepare_publish.side_effect = ValueError("플랫폼을 선택해주세요")
        resp = client.post(
            f"{BASE}/sess-001/prepare-publish",
            json={"platform_targets": ["bunjang"]},
        )
        assert resp.status_code == 400


class TestPublish:

    @pytest.mark.integration
    def test_returns_completed(self, client):
        resp = client.post(f"{BASE}/sess-001/publish")
        assert resp.status_code == 200
        assert resp.json()["status"] == "completed"

    @pytest.mark.integration
    def test_publish_execution_error_maps_to_502(self, client, mock_svc):
        mock_svc.publish_session.side_effect = PublishExecutionError("publish failed")
        resp = client.post(f"{BASE}/sess-001/publish")
        assert resp.status_code == 502

    @pytest.mark.integration
    def test_invalid_transition_maps_to_409(self, client, mock_svc):
        mock_svc.publish_session.side_effect = InvalidStateTransitionError("wrong state")
        resp = client.post(f"{BASE}/sess-001/publish")
        assert resp.status_code == 409


class TestUpdateSaleStatus:

    @pytest.mark.integration
    def test_returns_sale_status_updated(self, client):
        resp = client.post(
            f"{BASE}/sess-001/sale-status",
            json={"sale_status": "sold"},
        )
        assert resp.status_code == 200

    @pytest.mark.integration
    def test_missing_sale_status_returns_422(self, client):
        resp = client.post(f"{BASE}/sess-001/sale-status", json={})
        assert resp.status_code == 422

    @pytest.mark.integration
    def test_value_error_maps_to_400(self, client, mock_svc):
        mock_svc.update_sale_status.side_effect = ValueError("invalid status")
        resp = client.post(
            f"{BASE}/sess-001/sale-status",
            json={"sale_status": "sold"},
        )
        assert resp.status_code == 400

    @pytest.mark.integration
    def test_session_not_found_maps_to_404(self, client, mock_svc):
        mock_svc.update_sale_status.side_effect = SessionNotFoundError("not found")
        resp = client.post(
            f"{BASE}/sess-001/sale-status",
            json={"sale_status": "sold"},
        )
        assert resp.status_code == 404
