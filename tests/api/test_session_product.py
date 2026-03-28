"""세션 상품 API 테스트 — 이미지 업로드, 분석, 상품 확정, 직접 입력."""
import pytest

from app.domain.exceptions import InvalidStateTransitionError, SessionNotFoundError
from tests.api.conftest import BASE


class TestUploadImages:

    @pytest.mark.integration
    def test_returns_images_uploaded_status(self, client):
        resp = client.post(
            f"{BASE}/sess-001/images",
            files=[("files", ("test.jpg", b"fake-image-data", "image/jpeg"))],
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "images_uploaded"

    @pytest.mark.integration
    def test_missing_files_returns_422(self, client):
        resp = client.post(f"{BASE}/sess-001/images")
        assert resp.status_code == 422

    @pytest.mark.integration
    def test_invalid_transition_maps_to_409(self, client, mock_svc):
        mock_svc.attach_images.side_effect = InvalidStateTransitionError("wrong state")
        resp = client.post(
            f"{BASE}/sess-001/images",
            files=[("files", ("test.jpg", b"fake-image-data", "image/jpeg"))],
        )
        assert resp.status_code == 409


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
        mock_svc.confirm_product.assert_called_once()
        call_kwargs = mock_svc.confirm_product.call_args.kwargs
        assert call_kwargs["session_id"] == "sess-001"
        assert call_kwargs["candidate_index"] == 0

    @pytest.mark.integration
    def test_invalid_transition_maps_to_409(self, client, mock_svc):
        mock_svc.confirm_product.side_effect = InvalidStateTransitionError("wrong state")
        resp = client.post(
            f"{BASE}/sess-001/confirm-product",
            json={"candidate_index": 0},
        )
        assert resp.status_code == 409


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
