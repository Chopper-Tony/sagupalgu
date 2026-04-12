"""마켓 헬퍼 함수 + sale_status 전이 규칙 + goal_strategy 확장 unit 테스트."""
import pytest
from datetime import datetime, timezone, timedelta

from app.repositories.session_repository import (
    SALE_STATUS_TRANSITIONS,
    _get_sale_status,
)
from app.domain.goal_strategy import (
    INQUIRY_REPLY_TEMPLATES,
    get_inquiry_reply_template,
)


# ── _get_sale_status ──────────────────────────────────────


class TestGetSaleStatus:
    @pytest.mark.unit
    def test_default_available(self):
        assert _get_sale_status({}) == "available"

    @pytest.mark.unit
    def test_no_listing_data(self):
        assert _get_sale_status({"listing_data_jsonb": None}) == "available"

    @pytest.mark.unit
    def test_empty_listing_data(self):
        assert _get_sale_status({"listing_data_jsonb": {}}) == "available"

    @pytest.mark.unit
    def test_explicit_available(self):
        session = {"listing_data_jsonb": {"sale_status": "available"}}
        assert _get_sale_status(session) == "available"

    @pytest.mark.unit
    def test_sold(self):
        session = {"listing_data_jsonb": {"sale_status": "sold"}}
        assert _get_sale_status(session) == "sold"

    @pytest.mark.unit
    def test_reserved(self):
        session = {"listing_data_jsonb": {"sale_status": "reserved"}}
        assert _get_sale_status(session) == "reserved"


# ── SALE_STATUS_TRANSITIONS ───────────────────────────────


class TestSaleStatusTransitions:
    @pytest.mark.unit
    def test_available_can_go_to_reserved_and_sold(self):
        assert "reserved" in SALE_STATUS_TRANSITIONS["available"]
        assert "sold" in SALE_STATUS_TRANSITIONS["available"]

    @pytest.mark.unit
    def test_reserved_can_go_to_sold_and_available(self):
        assert "sold" in SALE_STATUS_TRANSITIONS["reserved"]
        assert "available" in SALE_STATUS_TRANSITIONS["reserved"]

    @pytest.mark.unit
    def test_sold_cannot_transition(self):
        assert SALE_STATUS_TRANSITIONS["sold"] == []

    @pytest.mark.unit
    def test_all_states_defined(self):
        assert set(SALE_STATUS_TRANSITIONS.keys()) == {"available", "reserved", "sold"}


# ── goal_strategy: inquiry reply templates ────────────────


class TestInquiryReplyTemplates:
    @pytest.mark.unit
    def test_all_goals_have_templates(self):
        for goal in ["fast_sell", "balanced", "profit_max"]:
            assert goal in INQUIRY_REPLY_TEMPLATES

    @pytest.mark.unit
    def test_each_goal_has_required_types(self):
        for goal, templates in INQUIRY_REPLY_TEMPLATES.items():
            assert "nego" in templates, f"{goal} missing nego"
            assert "condition" in templates, f"{goal} missing condition"
            assert "default" in templates, f"{goal} missing default"

    @pytest.mark.unit
    @pytest.mark.parametrize("goal", ["fast_sell", "balanced", "profit_max"])
    def test_get_template_nego(self, goal):
        result = get_inquiry_reply_template(goal, "nego", 100000)
        assert isinstance(result, str)
        assert len(result) > 10

    @pytest.mark.unit
    def test_get_template_default_fallback(self):
        result = get_inquiry_reply_template("balanced", "unknown_type", 50000)
        assert isinstance(result, str)
        assert len(result) > 0

    @pytest.mark.unit
    def test_get_template_unknown_goal_falls_back_to_balanced(self):
        result = get_inquiry_reply_template("nonexistent", "default", 0)
        expected = get_inquiry_reply_template("balanced", "default", 0)
        assert result == expected

    @pytest.mark.unit
    def test_nego_template_includes_discount(self):
        result = get_inquiry_reply_template("balanced", "nego", 100000)
        assert "95,000" in result


# ── _compute_copilot_suggestions (import from market_router) ─


class TestComputeCopilotSuggestions:
    """market_router의 _compute_copilot_suggestions 헬퍼 테스트."""

    @pytest.fixture
    def _import_fn(self):
        from app.api.market_router import _compute_copilot_suggestions
        return _compute_copilot_suggestions

    def _make_session(self, days_ago: int, price: int = 500000, sale_status: str = "available"):
        created = (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()
        return {
            "listing_data_jsonb": {
                "sale_status": sale_status,
                "canonical_listing": {"price": price},
            },
            "created_at": created,
        }

    @pytest.mark.unit
    def test_no_suggestions_for_new_listing(self, _import_fn):
        session = self._make_session(days_ago=1)
        assert _import_fn(session, inquiry_count=0) == []

    @pytest.mark.unit
    def test_price_suggestion_after_3_days_no_inquiry(self, _import_fn):
        session = self._make_session(days_ago=4)
        suggestions = _import_fn(session, inquiry_count=0)
        types = [s["type"] for s in suggestions]
        assert "price" in types

    @pytest.mark.unit
    def test_no_suggestion_if_has_inquiries(self, _import_fn):
        session = self._make_session(days_ago=5)
        suggestions = _import_fn(session, inquiry_count=3)
        price_suggestions = [s for s in suggestions if s["type"] == "price"]
        assert len(price_suggestions) == 0

    @pytest.mark.unit
    def test_title_suggestion_after_7_days(self, _import_fn):
        session = self._make_session(days_ago=8)
        suggestions = _import_fn(session, inquiry_count=0)
        types = [s["type"] for s in suggestions]
        assert "title" in types

    @pytest.mark.unit
    def test_relist_suggestion_after_14_days(self, _import_fn):
        session = self._make_session(days_ago=15)
        suggestions = _import_fn(session, inquiry_count=0)
        types = [s["type"] for s in suggestions]
        assert "relist" in types

    @pytest.mark.unit
    def test_no_suggestions_for_sold(self, _import_fn):
        session = self._make_session(days_ago=30, sale_status="sold")
        assert _import_fn(session, inquiry_count=0) == []

    @pytest.mark.unit
    def test_no_suggestions_without_created_at(self, _import_fn):
        session = {"listing_data_jsonb": {"sale_status": "available"}}
        assert _import_fn(session, inquiry_count=0) == []


# ── _extract_publish_results ──────────────────────────────


class TestExtractPublishResults:
    @pytest.fixture
    def _import_fn(self):
        from app.api.market_router import _extract_publish_results
        return _extract_publish_results

    @pytest.mark.unit
    def test_empty_when_no_results(self, _import_fn):
        assert _import_fn({}) == []

    @pytest.mark.unit
    def test_extracts_successful_platform(self, _import_fn):
        session = {
            "workflow_meta_jsonb": {
                "publish_results": {
                    "bunjang": {"success": True, "external_url": "https://bunjang.co.kr/123"},
                }
            }
        }
        results = _import_fn(session)
        assert len(results) == 1
        assert results[0]["platform"] == "bunjang"
        assert results[0]["success"] is True
        assert results[0]["external_url"] == "https://bunjang.co.kr/123"

    @pytest.mark.unit
    def test_extracts_failed_platform(self, _import_fn):
        session = {
            "workflow_meta_jsonb": {
                "publish_results": {
                    "joongna": {"success": False},
                }
            }
        }
        results = _import_fn(session)
        assert len(results) == 1
        assert results[0]["success"] is False

    @pytest.mark.unit
    def test_platform_name_mapping(self, _import_fn):
        session = {
            "workflow_meta_jsonb": {
                "publish_results": {
                    "bunjang": {"success": True},
                    "joongna": {"success": True},
                }
            }
        }
        results = _import_fn(session)
        names = {r["platform_name"] for r in results}
        assert names == {"번개장터", "중고나라"}


# ── _get_category + _get_price ────────────────────────────


class TestGetCategoryAndPrice:
    @pytest.mark.unit
    def test_get_category_from_confirmed_product(self):
        from app.api.market_router import _get_category
        session = {"product_data_jsonb": {"confirmed_product": {"category": "스마트폰"}}}
        assert _get_category(session) == "스마트폰"

    @pytest.mark.unit
    def test_get_category_empty(self):
        from app.api.market_router import _get_category
        assert _get_category({}) == ""

    @pytest.mark.unit
    def test_get_price_from_canonical(self):
        from app.api.market_router import _get_price
        session = {"listing_data_jsonb": {"canonical_listing": {"price": 500000}}}
        assert _get_price(session) == 500000

    @pytest.mark.unit
    def test_get_price_string_coercion(self):
        from app.api.market_router import _get_price
        session = {"listing_data_jsonb": {"canonical_listing": {"price": "300000"}}}
        assert _get_price(session) == 300000

    @pytest.mark.unit
    def test_get_price_empty(self):
        from app.api.market_router import _get_price
        assert _get_price({}) == 0

    @pytest.mark.unit
    def test_get_price_invalid_string(self):
        from app.api.market_router import _get_price
        session = {"listing_data_jsonb": {"canonical_listing": {"price": "invalid"}}}
        assert _get_price(session) == 0
