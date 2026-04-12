"""마켓 상태 불변성 + 멀티유저 권한 + API contract 테스트.

M151: 데모 중 터질 수 있는 edge case를 사전 차단.
"""
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.dependencies import (
    get_inquiry_repository,
    get_session_repository,
    get_session_service,
)
from app.main import app
from app.middleware.rate_limit import reset_rate_limiter


# ── 헬퍼 ──────────────────────────────────────────────


def _session(
    sid="sess-001", user_id="seller-1", sale_status=None, price=700000, title="테스트 상품",
):
    listing = {"canonical_listing": {"title": title, "price": price, "description": "설명", "tags": ["태그"]}}
    if sale_status:
        listing["sale_status"] = sale_status
    return {
        "id": sid,
        "user_id": user_id,
        "status": "completed",
        "product_data_jsonb": {"image_paths": ["/uploads/test.jpg"], "confirmed_product": {"category": "스마트폰"}},
        "listing_data_jsonb": listing,
        "workflow_meta_jsonb": {"publish_results": {"bunjang": {"success": True, "external_url": "https://bunjang.co.kr/1"}}},
        "created_at": "2026-04-01T12:00:00+00:00",
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
    repo.list_completed.return_value = ([_session()], 1)
    repo.search_completed.return_value = ([_session()], 1)
    repo.get_completed_by_id.return_value = _session()
    repo.get_by_id_and_user.return_value = _session()
    repo.list_by_user.return_value = [_session()]
    repo.update.return_value = _session()
    repo.update_sale_status.return_value = _session(sale_status="sold")
    return repo


@pytest.fixture
def mock_inq():
    repo = MagicMock()
    repo.create.return_value = {"id": "inq-001", "listing_id": "sess-001", "message": "테스트"}
    repo.list_by_listing.return_value = [
        {"id": "inq-001", "listing_id": "sess-001", "buyer_name": "구매자",
         "buyer_contact": "010-1234", "message": "네고?", "reply": None,
         "status": "open", "is_read": False, "last_reply_at": None, "created_at": "2026-04-01"},
    ]
    repo.get_by_id.return_value = {
        "id": "inq-001", "listing_id": "sess-001",
        "buyer_name": "구매자", "message": "네고?", "status": "open",
    }
    repo.reply.return_value = {"id": "inq-001", "status": "replied", "reply": "답변"}
    repo.count_by_listing.return_value = 1
    repo.count_unread.return_value = 1
    return repo


@pytest.fixture
def client(mock_repo, mock_inq):
    app.dependency_overrides[get_session_repository] = lambda: mock_repo
    app.dependency_overrides[get_inquiry_repository] = lambda: mock_inq
    with TestClient(app) as c:
        yield c


BASE = "/api/v1/market"
S1 = {"X-Dev-User-Id": "seller-1"}
S2 = {"X-Dev-User-Id": "seller-2"}


# ── 상태 꼬임 방어 ────────────────────────────────────


class TestStateSafety:
    @pytest.mark.unit
    def test_sold_item_rejects_inquiry(self, client, mock_repo):
        """sold 상품에 문의 생성 → 400."""
        mock_repo.get_completed_by_id.return_value = _session(sale_status="sold")
        resp = client.post(f"{BASE}/sess-001/inquiry", json={
            "name": "구매자", "contact": "010", "message": "구매 가능?"
        })
        assert resp.status_code == 400

    @pytest.mark.unit
    def test_sold_item_rejects_status_change(self, client, mock_repo):
        """sold 상품에 status 변경 → 409 (전이 불가)."""
        mock_repo.update_sale_status.return_value = "INVALID_TRANSITION"
        resp = client.patch(f"{BASE}/my-listings/sess-001/status",
                            json={"sale_status": "available"}, headers=S1)
        assert resp.status_code == 409

    @pytest.mark.unit
    def test_relist_creates_independent_session(self, client, mock_repo, mock_inq):
        """relist 후 새 세션은 원본 inquiry를 포함하지 않는다."""
        mock_svc = MagicMock()
        mock_svc.relist_session = AsyncMock(return_value={
            "session_id": "sess-new", "status": "completed",
        })
        app.dependency_overrides[get_session_service] = lambda: mock_svc

        resp = client.post(f"{BASE}/my-listings/sess-001/relist", headers=S1)
        assert resp.status_code == 200
        new_id = resp.json()["new_session"]["session_id"]
        assert new_id != "sess-001"

        # 새 세션의 inquiry 카운트는 0이어야 함
        mock_inq.count_by_listing.return_value = 0
        mock_repo.list_by_user.return_value = [_session(sid="sess-new")]
        resp2 = client.get(f"{BASE}/my-listings", headers=S1)
        assert resp2.status_code == 200
        items = resp2.json()["items"]
        if items:
            assert items[0].get("inquiry_count", 0) == 0

    @pytest.mark.unit
    def test_reserved_item_allows_reply(self, client, mock_repo):
        """reserved 상품에도 문의 응답은 가능하다."""
        mock_repo.get_by_id_and_user.return_value = _session(sale_status="reserved")
        resp = client.post(f"{BASE}/my-listings/sess-001/inquiries/inq-001/reply",
                           json={"reply": "내일 직거래해요!"}, headers=S1)
        assert resp.status_code == 200


# ── 멀티유저 권한 ─────────────────────────────────────


class TestMultiUserPermission:
    @pytest.mark.unit
    def test_seller2_cannot_see_seller1_inquiries(self, client, mock_repo):
        """seller-2가 seller-1 상품의 문의를 볼 수 없다."""
        mock_repo.get_by_id_and_user.return_value = None  # seller-2 소유 아님
        resp = client.get(f"{BASE}/my-listings/sess-001/inquiries", headers=S2)
        assert resp.status_code == 404

    @pytest.mark.unit
    def test_seller2_cannot_reply_to_seller1_inquiry(self, client, mock_repo):
        """seller-2가 seller-1의 문의에 답변할 수 없다."""
        mock_repo.get_by_id_and_user.return_value = None
        resp = client.post(f"{BASE}/my-listings/sess-001/inquiries/inq-001/reply",
                           json={"reply": "해킹"}, headers=S2)
        assert resp.status_code == 404

    @pytest.mark.unit
    def test_seller2_cannot_change_seller1_status(self, client, mock_repo):
        """seller-2가 seller-1 상품의 상태를 변경할 수 없다."""
        mock_repo.update_sale_status.return_value = None  # 소유권 불일치
        resp = client.patch(f"{BASE}/my-listings/sess-001/status",
                            json={"sale_status": "sold"}, headers=S2)
        assert resp.status_code == 404

    @pytest.mark.unit
    def test_seller2_cannot_relist_seller1_item(self, client):
        """seller-2가 seller-1 상품을 재등록할 수 없다."""
        mock_svc = MagicMock()
        from app.domain.exceptions import SessionNotFoundError
        mock_svc.relist_session = AsyncMock(side_effect=SessionNotFoundError("not found"))
        app.dependency_overrides[get_session_service] = lambda: mock_svc

        resp = client.post(f"{BASE}/my-listings/sess-001/relist", headers=S2)
        assert resp.status_code == 404

    @pytest.mark.unit
    def test_seller2_dashboard_is_empty(self, client, mock_repo):
        """seller-2의 대시보드는 seller-1 상품을 포함하지 않는다."""
        mock_repo.list_by_user.return_value = []  # seller-2는 상품 없음
        resp = client.get(f"{BASE}/my-listings", headers=S2)
        assert resp.status_code == 200
        assert resp.json()["total"] == 0


# ── API contract regression ───────────────────────────


class TestApiContract:
    @pytest.mark.unit
    def test_my_listings_response_has_required_fields(self, client):
        """my-listings 응답에 필수 필드가 항상 존재한다."""
        resp = client.get(f"{BASE}/my-listings", headers=S1)
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "total" in data
        if data["items"]:
            item = data["items"][0]
            for field in ["session_id", "title", "price", "sale_status", "inquiry_count",
                          "unread_inquiry_count", "copilot_suggestions", "publish_results"]:
                assert field in item, f"필수 필드 누락: {field}"

    @pytest.mark.unit
    def test_inquiry_list_response_shape(self, client):
        """inquiry 목록 응답에 listing 컨텍스트가 포함된다."""
        resp = client.get(f"{BASE}/my-listings/sess-001/inquiries", headers=S1)
        assert resp.status_code == 200
        data = resp.json()
        assert "inquiries" in data
        assert "listing" in data
        assert "total" in data
        listing = data["listing"]
        for field in ["listing_title", "listing_price", "thumbnail_url"]:
            assert field in listing, f"listing 컨텍스트 누락: {field}"

    @pytest.mark.unit
    def test_market_item_has_sale_status_and_category(self, client):
        """마켓 아이템에 sale_status와 category가 포함된다."""
        resp = client.get(BASE)
        assert resp.status_code == 200
        items = resp.json()["items"]
        if items:
            item = items[0]
            assert "sale_status" in item
            assert "category" in item

    @pytest.mark.unit
    def test_market_detail_has_seller_id_and_view_count(self, client):
        """마켓 상세에 seller_id와 view_count가 포함된다."""
        resp = client.get(f"{BASE}/sess-001")
        assert resp.status_code == 200
        data = resp.json()
        assert "seller_id" in data
        assert "view_count" in data
        assert "sale_status" in data

    @pytest.mark.unit
    def test_suggest_reply_response_shape(self, client):
        """suggest-reply 응답에 필수 필드가 존재한다."""
        resp = client.post(f"{BASE}/my-listings/sess-001/inquiries/inq-001/suggest-reply",
                           headers=S1)
        assert resp.status_code == 200
        data = resp.json()
        for field in ["suggested_reply", "inquiry_type", "goal", "source"]:
            assert field in data, f"suggest-reply 필드 누락: {field}"

    @pytest.mark.unit
    def test_seller_profile_response_shape(self, client):
        """판매자 프로필 응답 shape 검증."""
        resp = client.get(f"{BASE}/sellers/seller-1/profile")
        assert resp.status_code == 200
        data = resp.json()
        for field in ["user_id", "nickname", "total_listings", "sold_count"]:
            assert field in data, f"프로필 필드 누락: {field}"
