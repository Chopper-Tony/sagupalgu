"""마켓 API 통합 테스트 — TestClient + dependency_overrides."""
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.dependencies import get_session_repository, get_inquiry_repository, get_session_service
from app.main import app
from app.middleware.rate_limit import reset_rate_limiter


# ── 픽스처 ─────────────────────────────────────────────


def _make_completed_session(
    session_id="sess-001",
    user_id="seller-1",
    title="아이폰 15 프로",
    price=700000,
    sale_status=None,
    category="스마트폰",
    view_count=0,
    publish_results=None,
):
    listing_data = {
        "canonical_listing": {"title": title, "price": price, "description": "테스트 상품", "tags": ["아이폰"]},
    }
    if sale_status:
        listing_data["sale_status"] = sale_status
    if view_count:
        listing_data["view_count"] = view_count
    return {
        "id": session_id,
        "user_id": user_id,
        "status": "completed",
        "product_data_jsonb": {"image_paths": ["/uploads/test.jpg"], "confirmed_product": {"category": category}},
        "listing_data_jsonb": listing_data,
        "workflow_meta_jsonb": {"publish_results": publish_results or {}},
        "created_at": "2026-04-10T12:00:00+00:00",
    }


@pytest.fixture(autouse=True)
def _reset():
    reset_rate_limiter()
    yield
    reset_rate_limiter()
    app.dependency_overrides.clear()


@pytest.fixture
def mock_repo():
    repo = MagicMock()
    repo.list_completed.return_value = ([_make_completed_session()], 1)
    repo.search_completed.return_value = ([_make_completed_session()], 1)
    repo.get_completed_by_id.return_value = _make_completed_session()
    repo.get_by_id_and_user.return_value = _make_completed_session()
    repo.list_by_user.return_value = [_make_completed_session()]
    repo.update.return_value = _make_completed_session()
    repo.update_sale_status.return_value = _make_completed_session(sale_status="sold")
    return repo


@pytest.fixture
def mock_inquiry_repo():
    repo = MagicMock()
    repo.create.return_value = {"id": "inq-001", "listing_id": "sess-001", "message": "테스트"}
    repo.list_by_listing.return_value = []
    repo.count_by_listing.return_value = 0
    repo.count_unread.return_value = 0
    repo.get_by_id.return_value = {
        "id": "inq-001", "listing_id": "sess-001",
        "buyer_name": "구매자", "message": "네고 가능하세요?",
        "status": "open",
    }
    repo.reply.return_value = {"id": "inq-001", "status": "replied", "reply": "안녕하세요"}
    return repo


@pytest.fixture
def client(mock_repo, mock_inquiry_repo):
    app.dependency_overrides[get_session_repository] = lambda: mock_repo
    app.dependency_overrides[get_inquiry_repository] = lambda: mock_inquiry_repo
    with TestClient(app) as c:
        yield c


BASE = "/api/v1/market"


# ── 공개 API ──────────────────────────────────────────


class TestMarketList:
    @pytest.mark.unit
    def test_list_returns_items(self, client):
        resp = client.get(BASE)
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert data["total"] >= 0

    @pytest.mark.unit
    def test_list_with_search(self, client):
        resp = client.get(BASE, params={"q": "아이폰"})
        assert resp.status_code == 200

    @pytest.mark.unit
    def test_list_with_sale_status_filter(self, client):
        resp = client.get(BASE, params={"sale_status": "available"})
        assert resp.status_code == 200

    @pytest.mark.unit
    def test_list_with_category(self, client):
        resp = client.get(BASE, params={"category": "스마트폰"})
        assert resp.status_code == 200

    @pytest.mark.unit
    def test_list_with_sort(self, client):
        resp = client.get(BASE, params={"sort": "price_asc"})
        assert resp.status_code == 200


class TestMarketDetail:
    @pytest.mark.unit
    def test_detail_returns_item(self, client):
        resp = client.get(f"{BASE}/sess-001")
        assert resp.status_code == 200
        data = resp.json()
        assert data["session_id"] == "sess-001"
        assert "sale_status" in data
        assert "seller_id" in data

    @pytest.mark.unit
    def test_detail_not_found(self, client, mock_repo):
        mock_repo.get_completed_by_id.return_value = None
        resp = client.get(f"{BASE}/nonexistent")
        assert resp.status_code == 404


class TestMarketInquiry:
    @pytest.mark.unit
    def test_submit_inquiry(self, client):
        resp = client.post(f"{BASE}/sess-001/inquiry", json={
            "name": "구매자", "contact": "010-1234-5678", "message": "상태 어떤가요?"
        })
        assert resp.status_code == 200
        assert resp.json()["success"] is True
        assert "inquiry_id" in resp.json()

    @pytest.mark.unit
    def test_submit_inquiry_sold_rejected(self, client, mock_repo):
        mock_repo.get_completed_by_id.return_value = _make_completed_session(sale_status="sold")
        resp = client.post(f"{BASE}/sess-001/inquiry", json={
            "name": "구매자", "contact": "010", "message": "구매 가능?"
        })
        assert resp.status_code == 400

    @pytest.mark.unit
    def test_submit_inquiry_validation(self, client):
        resp = client.post(f"{BASE}/sess-001/inquiry", json={"name": "", "contact": "", "message": ""})
        assert resp.status_code == 422


# ── 판매자 전용 API (인증 필요 — dev bypass) ──────────


class TestMyListings:
    @pytest.mark.unit
    def test_my_listings(self, client):
        resp = client.get(f"{BASE}/my-listings", headers={"X-Dev-User-Id": "seller-1"})
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "total" in data

    @pytest.mark.unit
    def test_my_listings_with_filter(self, client):
        resp = client.get(f"{BASE}/my-listings", params={"sale_status_filter": "available"},
                          headers={"X-Dev-User-Id": "seller-1"})
        assert resp.status_code == 200


class TestStatusChange:
    @pytest.mark.unit
    def test_change_to_sold(self, client):
        resp = client.patch(f"{BASE}/my-listings/sess-001/status",
                            json={"sale_status": "sold"},
                            headers={"X-Dev-User-Id": "seller-1"})
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    @pytest.mark.unit
    def test_change_not_found(self, client, mock_repo):
        mock_repo.update_sale_status.return_value = None
        resp = client.patch(f"{BASE}/my-listings/sess-001/status",
                            json={"sale_status": "sold"},
                            headers={"X-Dev-User-Id": "seller-1"})
        assert resp.status_code == 404

    @pytest.mark.unit
    def test_change_invalid_transition(self, client, mock_repo):
        from app.domain.exceptions import InvalidStateTransitionError
        mock_repo.update_sale_status.side_effect = InvalidStateTransitionError("전이 불가")
        resp = client.patch(f"{BASE}/my-listings/sess-001/status",
                            json={"sale_status": "reserved"},
                            headers={"X-Dev-User-Id": "seller-1"})
        assert resp.status_code == 409


class TestInquiryManagement:
    @pytest.mark.unit
    def test_list_inquiries(self, client):
        resp = client.get(f"{BASE}/my-listings/sess-001/inquiries",
                          headers={"X-Dev-User-Id": "seller-1"})
        assert resp.status_code == 200
        assert "inquiries" in resp.json()

    @pytest.mark.unit
    def test_reply_to_inquiry(self, client):
        resp = client.post(f"{BASE}/my-listings/sess-001/inquiries/inq-001/reply",
                           json={"reply": "안녕하세요! 상태 좋습니다."},
                           headers={"X-Dev-User-Id": "seller-1"})
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    @pytest.mark.unit
    def test_reply_not_owner(self, client, mock_repo):
        mock_repo.get_by_id_and_user.return_value = None
        resp = client.post(f"{BASE}/my-listings/sess-001/inquiries/inq-001/reply",
                           json={"reply": "답변"},
                           headers={"X-Dev-User-Id": "seller-2"})
        assert resp.status_code == 404


class TestSuggestReply:
    @pytest.mark.unit
    def test_suggest_reply_fallback(self, client):
        """LLM 없이 fallback 템플릿이 반환되는지 확인."""
        resp = client.post(f"{BASE}/my-listings/sess-001/inquiries/inq-001/suggest-reply",
                           headers={"X-Dev-User-Id": "seller-1"})
        assert resp.status_code == 200
        data = resp.json()
        assert "suggested_reply" in data
        assert data["source"] in ("template", "llm")
        assert data["inquiry_type"] == "nego"  # "네고 가능하세요?" → nego


class TestRelist:
    @pytest.mark.unit
    def test_relist(self, client):
        from unittest.mock import AsyncMock
        mock_svc = MagicMock()
        mock_svc.relist_session = AsyncMock(return_value={"session_id": "sess-002", "status": "completed"})
        app.dependency_overrides[get_session_service] = lambda: mock_svc
        resp = client.post(f"{BASE}/my-listings/sess-001/relist",
                           headers={"X-Dev-User-Id": "seller-1"})
        assert resp.status_code == 200
        assert resp.json()["success"] is True


class TestSellerProfile:
    @pytest.mark.unit
    def test_get_profile(self, client):
        resp = client.get(f"{BASE}/sellers/seller-1/profile")
        assert resp.status_code == 200
        data = resp.json()
        assert data["user_id"] == "seller-1"
        assert "nickname" in data
        assert "total_listings" in data
        assert "sold_count" in data
