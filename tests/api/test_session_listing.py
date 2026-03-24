"""세션 판매글 API 테스트 — 생성, 재작성."""
import pytest

from app.domain.exceptions import ListingGenerationError, ListingRewriteError, SessionNotFoundError
from tests.api.conftest import BASE


class TestGenerateListing:

    @pytest.mark.integration
    def test_returns_draft_generated(self, client):
        resp = client.post(f"{BASE}/sess-001/generate-listing")
        assert resp.status_code == 200
        assert resp.json()["status"] == "draft_generated"

    @pytest.mark.integration
    def test_listing_generation_error_maps_to_500(self, client, mock_svc):
        mock_svc.generate_listing.side_effect = ListingGenerationError("LLM failed")
        resp = client.post(f"{BASE}/sess-001/generate-listing")
        assert resp.status_code == 500

    @pytest.mark.integration
    def test_session_not_found_maps_to_404(self, client, mock_svc):
        mock_svc.generate_listing.side_effect = SessionNotFoundError("no session")
        resp = client.post(f"{BASE}/sess-001/generate-listing")
        assert resp.status_code == 404


class TestRewriteListing:

    @pytest.mark.integration
    def test_returns_draft_generated(self, client):
        resp = client.post(
            f"{BASE}/sess-001/rewrite-listing",
            json={"instruction": "더 짧게 작성해주세요"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "draft_generated"

    @pytest.mark.integration
    def test_empty_instruction_returns_422(self, client):
        resp = client.post(
            f"{BASE}/sess-001/rewrite-listing",
            json={"instruction": ""},
        )
        assert resp.status_code == 422

    @pytest.mark.integration
    def test_missing_instruction_returns_422(self, client):
        resp = client.post(f"{BASE}/sess-001/rewrite-listing", json={})
        assert resp.status_code == 422

    @pytest.mark.integration
    def test_listing_rewrite_error_maps_to_500(self, client, mock_svc):
        mock_svc.rewrite_listing.side_effect = ListingRewriteError("rewrite failed")
        resp = client.post(
            f"{BASE}/sess-001/rewrite-listing",
            json={"instruction": "수정해주세요"},
        )
        assert resp.status_code == 500
