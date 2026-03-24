"""
보안·운영 강화 테스트

- CORSMiddleware: 응답 헤더 검증
- UploadImagesRequest 입력 검증: URL 형식, 빈 값, min_length
- PreparePublishRequest 플랫폼 검증: 허용값, 미지원 플랫폼, 빈 목록
- SaleStatusRequest: Literal 타입 강제
"""
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.dependencies import get_session_service
from app.main import app
from app.schemas.session import (
    PreparePublishRequest,
    SaleStatusRequest,
    UploadImagesRequest,
)

BASE = "/api/v1/sessions"


@pytest.fixture
def client():
    mock_svc = MagicMock()
    app.dependency_overrides[get_session_service] = lambda: mock_svc
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    app.dependency_overrides.clear()


# ─────────────────────────────────────────────────────────────────
# CORS
# ─────────────────────────────────────────────────────────────────

class TestCORS:

    @pytest.mark.integration
    def test_cors_header_present_for_known_origin(self, client):
        resp = client.get("/health", headers={"Origin": "http://localhost:5173"})
        # allow_origins=["*"] 이므로 Access-Control-Allow-Origin 포함
        assert "access-control-allow-origin" in resp.headers

    @pytest.mark.integration
    def test_preflight_options_returns_200(self, client):
        resp = client.options(
            "/health",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert resp.status_code in (200, 204)


# ─────────────────────────────────────────────────────────────────
# UploadImagesRequest 검증
# ─────────────────────────────────────────────────────────────────

class TestUploadImagesRequestValidation:

    @pytest.mark.unit
    def test_valid_https_url_accepted(self):
        req = UploadImagesRequest(image_urls=["https://example.com/img.jpg"])
        assert req.image_urls == ["https://example.com/img.jpg"]

    @pytest.mark.unit
    def test_valid_http_url_accepted(self):
        req = UploadImagesRequest(image_urls=["http://example.com/img.jpg"])
        assert req.image_urls[0].startswith("http://")

    @pytest.mark.unit
    def test_empty_list_rejected(self):
        with pytest.raises(ValidationError):
            UploadImagesRequest(image_urls=[])

    @pytest.mark.unit
    def test_non_http_url_rejected(self):
        with pytest.raises(ValidationError, match="HTTP"):
            UploadImagesRequest(image_urls=["ftp://example.com/img.jpg"])

    @pytest.mark.unit
    def test_empty_string_url_rejected(self):
        with pytest.raises(ValidationError, match="빈 URL"):
            UploadImagesRequest(image_urls=[""])

    @pytest.mark.unit
    def test_url_whitespace_stripped(self):
        req = UploadImagesRequest(image_urls=["  https://example.com/img.jpg  "])
        assert req.image_urls[0] == "https://example.com/img.jpg"

    @pytest.mark.integration
    def test_invalid_url_returns_422(self, client):
        resp = client.post(
            f"{BASE}/sess-001/images",
            json={"image_urls": ["not-a-url"]},
        )
        assert resp.status_code == 422

    @pytest.mark.integration
    def test_empty_list_returns_422(self, client):
        resp = client.post(
            f"{BASE}/sess-001/images",
            json={"image_urls": []},
        )
        assert resp.status_code == 422


# ─────────────────────────────────────────────────────────────────
# PreparePublishRequest 플랫폼 검증
# ─────────────────────────────────────────────────────────────────

class TestPreparePublishRequestValidation:

    @pytest.mark.unit
    def test_bunjang_accepted(self):
        req = PreparePublishRequest(platform_targets=["bunjang"])
        assert req.platform_targets == ["bunjang"]

    @pytest.mark.unit
    def test_joongna_accepted(self):
        req = PreparePublishRequest(platform_targets=["joongna"])
        assert req.platform_targets == ["joongna"]

    @pytest.mark.unit
    def test_both_platforms_accepted(self):
        req = PreparePublishRequest(platform_targets=["bunjang", "joongna"])
        assert len(req.platform_targets) == 2

    @pytest.mark.unit
    def test_empty_list_rejected(self):
        with pytest.raises(ValidationError):
            PreparePublishRequest(platform_targets=[])

    @pytest.mark.unit
    def test_unknown_platform_rejected(self):
        with pytest.raises(ValidationError, match="지원하지 않는 플랫폼"):
            PreparePublishRequest(platform_targets=["daangn"])

    @pytest.mark.unit
    def test_mixed_valid_invalid_rejected(self):
        with pytest.raises(ValidationError, match="지원하지 않는 플랫폼"):
            PreparePublishRequest(platform_targets=["bunjang", "unknown"])

    @pytest.mark.integration
    def test_unknown_platform_returns_422(self, client):
        resp = client.post(
            f"{BASE}/sess-001/prepare-publish",
            json={"platform_targets": ["daangn"]},
        )
        assert resp.status_code == 422


# ─────────────────────────────────────────────────────────────────
# SaleStatusRequest Literal 검증
# ─────────────────────────────────────────────────────────────────

class TestSaleStatusRequestValidation:

    @pytest.mark.unit
    def test_sold_accepted(self):
        req = SaleStatusRequest(sale_status="sold")
        assert req.sale_status == "sold"

    @pytest.mark.unit
    def test_unsold_accepted(self):
        req = SaleStatusRequest(sale_status="unsold")
        assert req.sale_status == "unsold"

    @pytest.mark.unit
    def test_in_progress_accepted(self):
        req = SaleStatusRequest(sale_status="in_progress")
        assert req.sale_status == "in_progress"

    @pytest.mark.unit
    def test_invalid_value_rejected(self):
        with pytest.raises(ValidationError):
            SaleStatusRequest(sale_status="cancelled")

    @pytest.mark.integration
    def test_invalid_sale_status_returns_422(self, client):
        resp = client.post(
            f"{BASE}/sess-001/sale-status",
            json={"sale_status": "cancelled"},
        )
        assert resp.status_code == 422
