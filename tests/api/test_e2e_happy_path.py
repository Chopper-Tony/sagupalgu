"""E2E Happy Path — 전체 세션 라이프사이클 API 체인 테스트.

세션 생성 → 이미지 업로드 → 분석 → 상품 확정 → 판매글 생성
→ 게시 준비 → 게시 → 판매 상태 업데이트까지 1경로 검증.
"""
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.dependencies import get_session_service
from app.main import app
from tests.api.conftest import BASE, SESSION_UI

# 프론트엔드 SessionResponse 필수 필드
FRONTEND_FIELDS = {
    "session_id", "status", "needs_user_input",
    "clarification_prompt", "product_candidates", "confirmed_product",
    "canonical_listing", "market_context", "platform_results",
    "optimization_suggestion", "image_urls", "selected_platforms",
}


def _make_response(status: str, **overrides) -> dict:
    """상태별 mock 응답을 생성한다."""
    return {**SESSION_UI, "status": status, **overrides}


@pytest.fixture
def e2e_svc():
    """E2E happy path에 맞춘 단계별 mock 서비스."""
    svc = MagicMock()
    svc.create_session = AsyncMock(return_value=_make_response("session_created"))
    svc.attach_images = AsyncMock(return_value=_make_response(
        "images_uploaded",
        image_urls=["/uploads/sess-001/img1.jpg"],
    ))
    svc.analyze_session = AsyncMock(return_value=_make_response(
        "awaiting_product_confirmation",
        product_candidates=[
            {"brand": "Apple", "model": "iPhone 15 Pro", "category": "smartphone", "confidence": 0.92},
        ],
        clarification_prompt="상품 정보를 확인해 주세요.",
        needs_user_input=True,
    ))
    svc.provide_product_info = AsyncMock(return_value=_make_response(
        "product_confirmed",
        confirmed_product={"brand": "Apple", "model": "iPhone 15 Pro", "category": "smartphone", "source": "user_input"},
        needs_user_input=False,
    ))
    svc.generate_listing = AsyncMock(return_value=_make_response(
        "draft_generated",
        canonical_listing={
            "title": "Apple iPhone 15 Pro 256GB 판매합니다",
            "description": "깨끗하게 사용했습니다. 구성품 전부 포함.",
            "price": 950000,
            "tags": ["iPhone15Pro", "Apple"],
            "images": ["/uploads/sess-001/img1.jpg"],
        },
        market_context={"median_price": 980000, "sample_count": 12, "price_band": [900000, 1100000]},
    ))
    svc.prepare_publish = AsyncMock(return_value=_make_response(
        "awaiting_publish_approval",
        selected_platforms=["bunjang", "joongna"],
    ))
    svc.publish_session = AsyncMock(return_value=_make_response(
        "completed",
        platform_results=[
            {"platform": "bunjang", "success": True, "url": "https://bunjang.co.kr/products/123"},
            {"platform": "joongna", "success": True, "url": "https://joongna.com/products/456"},
        ],
    ))
    svc.update_sale_status = AsyncMock(return_value=_make_response(
        "awaiting_sale_status_update",
        optimization_suggestion={"suggested_price": 900000, "reason": "7일 미판매", "days_elapsed": 7},
    ))
    return svc


@pytest.fixture
def e2e_client(e2e_svc):
    app.dependency_overrides[get_session_service] = lambda: e2e_svc
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


class TestE2EHappyPath:
    """전체 세션 라이프사이클을 순차 호출하여 상태 전이와 응답 shape을 검증."""

    @pytest.mark.integration
    def test_full_lifecycle(self, e2e_client):
        c = e2e_client

        # 1. 세션 생성
        r = c.post(BASE)
        assert r.status_code == 200
        d = r.json()
        assert d["status"] == "session_created"
        assert FRONTEND_FIELDS <= set(d.keys())
        sid = d["session_id"]

        # 2. 이미지 업로드
        r = c.post(
            f"{BASE}/{sid}/images",
            files=[("files", ("photo.jpg", b"fake-jpg", "image/jpeg"))],
        )
        assert r.status_code == 200
        d = r.json()
        assert d["status"] == "images_uploaded"
        assert len(d["image_urls"]) >= 1

        # 3. 분석
        r = c.post(f"{BASE}/{sid}/analyze")
        assert r.status_code == 200
        d = r.json()
        assert d["status"] == "awaiting_product_confirmation"
        assert len(d["product_candidates"]) >= 1
        assert d["needs_user_input"] is True

        # 4. 상품 확정
        r = c.post(
            f"{BASE}/{sid}/provide-product-info",
            json={"model": "iPhone 15 Pro", "brand": "Apple", "category": "smartphone"},
        )
        assert r.status_code == 200
        d = r.json()
        assert d["status"] == "product_confirmed"
        assert d["confirmed_product"] is not None
        assert d["confirmed_product"]["model"] == "iPhone 15 Pro"

        # 5. 판매글 생성
        r = c.post(f"{BASE}/{sid}/generate-listing")
        assert r.status_code == 200
        d = r.json()
        assert d["status"] == "draft_generated"
        listing = d["canonical_listing"]
        assert listing is not None
        assert "title" in listing
        assert "price" in listing
        assert listing["price"] > 0

        # 6. 게시 준비
        r = c.post(
            f"{BASE}/{sid}/prepare-publish",
            json={"platform_targets": ["bunjang", "joongna"]},
        )
        assert r.status_code == 200
        d = r.json()
        assert d["status"] == "awaiting_publish_approval"

        # 7. 게시
        r = c.post(f"{BASE}/{sid}/publish")
        assert r.status_code == 200
        d = r.json()
        assert d["status"] == "completed"
        results = d["platform_results"]
        assert len(results) == 2
        assert all(pr["success"] for pr in results)

        # 8. 판매 상태 업데이트
        r = c.post(
            f"{BASE}/{sid}/sale-status",
            json={"sale_status": "unsold"},
        )
        assert r.status_code == 200
        d = r.json()
        assert d["status"] == "awaiting_sale_status_update"


class TestE2EStatusTransitions:
    """각 단계의 상태 전이가 올바른 순서인지 검증."""

    EXPECTED_TRANSITIONS = [
        "session_created",
        "images_uploaded",
        "awaiting_product_confirmation",
        "product_confirmed",
        "draft_generated",
        "awaiting_publish_approval",
        "completed",
        "awaiting_sale_status_update",
    ]

    @pytest.mark.integration
    def test_status_order(self, e2e_client):
        c = e2e_client
        statuses = []

        statuses.append(c.post(BASE).json()["status"])
        statuses.append(c.post(f"{BASE}/sess-001/images", files=[("files", ("x.jpg", b"x", "image/jpeg"))]).json()["status"])
        statuses.append(c.post(f"{BASE}/sess-001/analyze").json()["status"])
        statuses.append(c.post(f"{BASE}/sess-001/provide-product-info", json={"model": "X"}).json()["status"])
        statuses.append(c.post(f"{BASE}/sess-001/generate-listing").json()["status"])
        statuses.append(c.post(f"{BASE}/sess-001/prepare-publish", json={"platform_targets": ["bunjang"]}).json()["status"])
        statuses.append(c.post(f"{BASE}/sess-001/publish").json()["status"])
        statuses.append(c.post(f"{BASE}/sess-001/sale-status", json={"sale_status": "sold"}).json()["status"])

        assert statuses == self.EXPECTED_TRANSITIONS


class TestE2EResponseShape:
    """모든 단계 응답이 프론트엔드 필수 필드를 포함하는지 검증."""

    @pytest.mark.integration
    def test_all_steps_have_frontend_fields(self, e2e_client):
        c = e2e_client
        steps = [
            lambda: c.post(BASE),
            lambda: c.post(f"{BASE}/sess-001/images", files=[("files", ("x.jpg", b"x", "image/jpeg"))]),
            lambda: c.post(f"{BASE}/sess-001/analyze"),
            lambda: c.post(f"{BASE}/sess-001/provide-product-info", json={"model": "X"}),
            lambda: c.post(f"{BASE}/sess-001/generate-listing"),
            lambda: c.post(f"{BASE}/sess-001/prepare-publish", json={"platform_targets": ["bunjang"]}),
            lambda: c.post(f"{BASE}/sess-001/publish"),
            lambda: c.post(f"{BASE}/sess-001/sale-status", json={"sale_status": "sold"}),
        ]
        for i, step in enumerate(steps):
            resp = step()
            assert resp.status_code == 200, f"Step {i} failed: {resp.status_code}"
            missing = FRONTEND_FIELDS - set(resp.json().keys())
            assert missing == set(), f"Step {i} missing: {missing}"
