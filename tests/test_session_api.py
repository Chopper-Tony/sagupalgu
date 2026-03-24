"""
세션 API 통합 테스트 — TestClient + dependency_overrides

FastAPI HTTP 레이어(라우터 → 서비스 → 응답 스키마)를 검증한다.
SessionService는 MagicMock으로 대체하므로 외부 의존성 없음.

검증 항목:
- 정상 케이스: 상태 코드 200/201, 응답 필드(session_id·status) 존재
- 도메인 예외 → HTTP 코드 매핑: 404·409·500·502
- 입력 검증 오류: 422 (Pydantic)
- ValueError → 400 매핑
"""
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.dependencies import get_session_service
from app.domain.exceptions import (
    InvalidStateTransitionError,
    ListingGenerationError,
    ListingRewriteError,
    PublishExecutionError,
    SessionNotFoundError,
)
from app.main import app


# ── 공통 픽스처 ────────────────────────────────────────────────────

BASE = "/api/v1/sessions"

SESSION_UI = {
    "session_id": "sess-001",
    "status": "created",
    "checkpoint": None,
    "next_action": "upload_images",
    "needs_user_input": False,
    "user_input_prompt": None,
    "selected_platforms": [],
    "product": {
        "image_paths": [],
        "image_count": 0,
        "analysis_source": None,
        "candidates": [],
        "confirmed_product": None,
    },
    "listing": {
        "market_context": None,
        "strategy": None,
        "canonical_listing": None,
        "platform_packages": {},
        "optimization_suggestion": None,
    },
    "publish": {"results": {}, "diagnostics": []},
    "agent_trace": {"tool_calls": [], "rewrite_history": []},
    "debug": {"last_error": None},
}


@pytest.fixture
def mock_svc():
    svc = MagicMock()
    svc.create_session = AsyncMock(return_value=SESSION_UI)
    svc.get_session = AsyncMock(return_value=SESSION_UI)
    svc.attach_images = AsyncMock(return_value={**SESSION_UI, "status": "images_uploaded"})
    svc.analyze_session = AsyncMock(return_value={**SESSION_UI, "status": "awaiting_product_confirmation"})
    svc.confirm_product = AsyncMock(return_value={**SESSION_UI, "status": "product_confirmed"})
    svc.provide_product_info = AsyncMock(return_value={**SESSION_UI, "status": "product_confirmed"})
    svc.generate_listing = AsyncMock(return_value={**SESSION_UI, "status": "draft_generated"})
    svc.rewrite_listing = AsyncMock(return_value={**SESSION_UI, "status": "draft_generated"})
    svc.prepare_publish = AsyncMock(return_value={**SESSION_UI, "status": "awaiting_publish_approval"})
    svc.publish_session = AsyncMock(return_value={**SESSION_UI, "status": "completed"})
    svc.update_sale_status = AsyncMock(return_value={**SESSION_UI, "status": "awaiting_sale_status_update"})
    return svc


@pytest.fixture
def client(mock_svc):
    app.dependency_overrides[get_session_service] = lambda: mock_svc
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# ── 헬스체크 ───────────────────────────────────────────────────────

class TestHealth:

    @pytest.mark.integration
    def test_health_ok(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


# ── POST /sessions ─────────────────────────────────────────────────

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


# ── GET /sessions/{id} ─────────────────────────────────────────────

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


# ── POST /sessions/{id}/images ─────────────────────────────────────

class TestUploadImages:

    @pytest.mark.integration
    def test_returns_images_uploaded_status(self, client):
        resp = client.post(
            f"{BASE}/sess-001/images",
            json={"image_urls": ["https://example.com/img.jpg"]},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "images_uploaded"

    @pytest.mark.integration
    def test_missing_image_urls_returns_422(self, client):
        resp = client.post(f"{BASE}/sess-001/images", json={})
        assert resp.status_code == 422

    @pytest.mark.integration
    def test_invalid_transition_maps_to_409(self, client, mock_svc):
        mock_svc.attach_images.side_effect = InvalidStateTransitionError("wrong state")
        resp = client.post(
            f"{BASE}/sess-001/images",
            json={"image_urls": ["https://example.com/img.jpg"]},
        )
        assert resp.status_code == 409


# ── POST /sessions/{id}/analyze ───────────────────────────────────

class TestAnalyzeSession:

    @pytest.mark.integration
    def test_returns_awaiting_confirmation(self, client):
        resp = client.post(f"{BASE}/sess-001/analyze")
        assert resp.status_code == 200
        assert resp.json()["status"] == "awaiting_product_confirmation"

    @pytest.mark.integration
    def test_session_not_found_maps_to_404(self, client, mock_svc):
        mock_svc.analyze_session.side_effect = SessionNotFoundError("not found")
        resp = client.post(f"{BASE}/missing/analyze")
        assert resp.status_code == 404

    @pytest.mark.integration
    def test_value_error_maps_to_400(self, client, mock_svc):
        mock_svc.analyze_session.side_effect = ValueError("이미지가 없습니다")
        resp = client.post(f"{BASE}/sess-001/analyze")
        assert resp.status_code == 400


# ── POST /sessions/{id}/confirm-product ───────────────────────────

class TestConfirmProduct:

    @pytest.mark.integration
    def test_returns_product_confirmed(self, client):
        resp = client.post(
            f"{BASE}/sess-001/confirm-product",
            json={"candidate_index": 0},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "product_confirmed"

    @pytest.mark.integration
    def test_default_candidate_index_is_zero(self, client, mock_svc):
        resp = client.post(f"{BASE}/sess-001/confirm-product", json={})
        assert resp.status_code == 200
        mock_svc.confirm_product.assert_called_once_with(
            session_id="sess-001", candidate_index=0
        )

    @pytest.mark.integration
    def test_invalid_transition_maps_to_409(self, client, mock_svc):
        mock_svc.confirm_product.side_effect = InvalidStateTransitionError("wrong state")
        resp = client.post(
            f"{BASE}/sess-001/confirm-product",
            json={"candidate_index": 0},
        )
        assert resp.status_code == 409


# ── POST /sessions/{id}/provide-product-info ──────────────────────

class TestProvideProductInfo:

    @pytest.mark.integration
    def test_returns_product_confirmed(self, client):
        resp = client.post(
            f"{BASE}/sess-001/provide-product-info",
            json={"model": "갤럭시 S24", "brand": "Samsung", "category": "smartphone"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "product_confirmed"

    @pytest.mark.integration
    def test_missing_model_returns_422(self, client):
        resp = client.post(
            f"{BASE}/sess-001/provide-product-info",
            json={"brand": "Samsung"},
        )
        assert resp.status_code == 422

    @pytest.mark.integration
    def test_value_error_maps_to_400(self, client, mock_svc):
        mock_svc.provide_product_info.side_effect = ValueError("모델명은 필수입니다")
        resp = client.post(
            f"{BASE}/sess-001/provide-product-info",
            json={"model": "  "},
        )
        assert resp.status_code == 400


# ── POST /sessions/{id}/generate-listing ─────────────────────────

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


# ── POST /sessions/{id}/rewrite-listing ──────────────────────────

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


# ── POST /sessions/{id}/prepare-publish ──────────────────────────

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
            json={"platform_targets": []},
        )
        assert resp.status_code == 400


# ── POST /sessions/{id}/publish ──────────────────────────────────

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


# ── POST /sessions/{id}/sale-status ──────────────────────────────

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
            json={"sale_status": "invalid"},
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
