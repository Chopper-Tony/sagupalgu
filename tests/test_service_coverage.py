"""
M64: 서비스 레이어 테스트 커버리지 확충

커버리지 부족 모듈:
- session_ui.py — UI 응답 평탄화
- publish_service.py — build_platform_packages
- optimization_service.py — run_post_sale_optimization
- recovery_service.py — run_recovery
"""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from copy import deepcopy

from app.services.session_ui import build_session_ui_response


# ─────────────────────────────────────────────────────────────────
# session_ui: build_session_ui_response
# ─────────────────────────────────────────────────────────────────

def _make_session(**overrides):
    base = {
        "id": "sess-123",
        "status": "draft_generated",
        "selected_platforms_jsonb": ["bunjang", "joongna"],
        "product_data_jsonb": {
            "image_paths": ["/img/a.jpg"],
            "candidates": [{"brand": "Apple", "model": "iPhone"}],
            "confirmed_product": {"brand": "Apple", "model": "iPhone", "category": "phone"},
            "needs_user_input": False,
            "analysis_source": "vision",
        },
        "listing_data_jsonb": {
            "canonical_listing": {"title": "test", "price": 100000},
            "market_context": {"median_price": 120000},
            "strategy": {"recommended_price": 100000},
            "platform_packages": {},
        },
        "workflow_meta_jsonb": {
            "checkpoint": "C_prepared",
            "last_error": None,
            "tool_calls": [{"tool_name": "t1"}],
            "rewrite_history": [],
            "decision_rationale": ["reason"],
            "plan": {"focus": "test"},
            "critic_score": 88,
            "critic_feedback": [{"type": "title"}],
            "publish_results": {
                "bunjang": {"success": True, "external_url": "https://bj.com/1"},
                "joongna": {"success": False, "error_message": "timeout"},
            },
        },
    }
    base.update(overrides)
    return base


class TestBuildSessionUiResponse:

    @pytest.mark.unit
    def test_basic_fields(self):
        resp = build_session_ui_response(_make_session())
        assert resp["session_id"] == "sess-123"
        assert resp["status"] == "draft_generated"
        assert resp["checkpoint"] == "C_prepared"
        assert resp["needs_user_input"] is False

    @pytest.mark.unit
    def test_session_id_fallback(self):
        """id가 없으면 session_id 사용."""
        s = _make_session()
        del s["id"]
        s["session_id"] = "fallback-id"
        resp = build_session_ui_response(s)
        assert resp["session_id"] == "fallback-id"

    @pytest.mark.unit
    def test_flattened_product_fields(self):
        resp = build_session_ui_response(_make_session())
        assert resp["image_urls"] == ["/img/a.jpg"]
        assert len(resp["product_candidates"]) == 1
        assert resp["confirmed_product"]["brand"] == "Apple"

    @pytest.mark.unit
    def test_flattened_listing_fields(self):
        resp = build_session_ui_response(_make_session())
        assert resp["canonical_listing"]["title"] == "test"
        assert resp["market_context"]["median_price"] == 120000

    @pytest.mark.unit
    def test_publish_results_transformation(self):
        """dict → list 변환, platform/success/url/error 매핑."""
        resp = build_session_ui_response(_make_session())
        results = resp["platform_results"]
        assert len(results) == 2
        bj = next(r for r in results if r["platform"] == "bunjang")
        jn = next(r for r in results if r["platform"] == "joongna")
        assert bj["success"] is True
        assert bj["url"] == "https://bj.com/1"
        assert jn["success"] is False
        assert jn["error"] == "timeout"

    @pytest.mark.unit
    def test_agent_trace_fields(self):
        resp = build_session_ui_response(_make_session())
        trace = resp["agent_trace"]
        assert len(trace["tool_calls"]) == 1
        assert trace["decision_rationale"] == ["reason"]
        assert trace["plan"]["focus"] == "test"
        assert trace["critic_score"] == 88
        assert len(trace["critic_feedback"]) == 1

    @pytest.mark.unit
    def test_nested_fields(self):
        resp = build_session_ui_response(_make_session())
        assert resp["product"]["analysis_source"] == "vision"
        assert resp["listing"]["strategy"]["recommended_price"] == 100000
        assert "bunjang" in resp["publish"]["results"]

    @pytest.mark.unit
    def test_empty_session(self):
        """모든 JSONB가 비어있어도 에러 없이 기본값 반환."""
        resp = build_session_ui_response({
            "id": "empty",
            "status": "session_created",
            "product_data_jsonb": {},
            "listing_data_jsonb": {},
            "workflow_meta_jsonb": {},
        })
        assert resp["session_id"] == "empty"
        assert resp["image_urls"] == []
        assert resp["product_candidates"] == []
        assert resp["confirmed_product"] is None
        assert resp["canonical_listing"] is None
        assert resp["platform_results"] == []
        assert resp["agent_trace"]["tool_calls"] == []


# ─────────────────────────────────────────────────────────────────
# publish_service: build_platform_packages
# ─────────────────────────────────────────────────────────────────

class TestBuildPlatformPackages:

    def _make_service(self):
        from app.services.publish_service import PublishService
        return PublishService()

    @pytest.mark.unit
    def test_bunjang_price_markup(self):
        svc = self._make_service()
        canonical = {"title": "t", "description": "d", "price": 100000, "images": []}
        result = svc.build_platform_packages(canonical, ["bunjang"])
        # 수수료 3.5% 보전: 100000 * 1.035 = 103500 → 천 단위 반올림 → 103000
        assert result["bunjang"]["price"] == 103000

    @pytest.mark.unit
    def test_joongna_price_same(self):
        svc = self._make_service()
        canonical = {"title": "t", "description": "d", "price": 100000, "images": []}
        result = svc.build_platform_packages(canonical, ["joongna"])
        assert result["joongna"]["price"] == 100000

    @pytest.mark.unit
    def test_daangn_price_discount(self):
        svc = self._make_service()
        canonical = {"title": "t", "description": "d", "price": 100000, "images": []}
        result = svc.build_platform_packages(canonical, ["daangn"])
        assert result["daangn"]["price"] == 96000

    @pytest.mark.unit
    def test_daangn_price_floor_zero(self):
        """가격이 매우 낮으면 음수 방지."""
        svc = self._make_service()
        canonical = {"title": "t", "description": "d", "price": 2000, "images": []}
        result = svc.build_platform_packages(canonical, ["daangn"])
        assert result["daangn"]["price"] >= 0

    @pytest.mark.unit
    def test_multi_platform(self):
        svc = self._make_service()
        canonical = {"title": "t", "description": "d", "price": 50000, "images": ["a.jpg"]}
        result = svc.build_platform_packages(canonical, ["bunjang", "joongna"])
        assert "bunjang" in result
        assert "joongna" in result
        assert result["bunjang"]["price"] == 52000  # 3.5% 수수료 보전
        assert result["joongna"]["price"] == 50000

    @pytest.mark.unit
    def test_package_fields(self):
        svc = self._make_service()
        canonical = {"title": "제목", "description": "설명", "price": 10000, "images": ["a.jpg"]}
        result = svc.build_platform_packages(canonical, ["bunjang"])
        pkg = result["bunjang"]
        assert pkg["title"] == "제목"
        assert pkg["body"] == "설명"
        assert pkg["images"] == ["a.jpg"]

    @pytest.mark.unit
    def test_empty_platforms(self):
        svc = self._make_service()
        result = svc.build_platform_packages({"price": 100}, [])
        assert result == {}

    @pytest.mark.unit
    def test_missing_canonical_fields(self):
        """canonical_listing에 키가 없어도 기본값 처리."""
        svc = self._make_service()
        result = svc.build_platform_packages({}, ["bunjang"])
        pkg = result["bunjang"]
        assert pkg["price"] >= 0


# ─────────────────────────────────────────────────────────────────
# optimization_service: run_post_sale_optimization
# ─────────────────────────────────────────────────────────────────

class TestOptimizationService:

    @pytest.mark.unit
    def test_returns_expected_structure(self):
        from app.services.optimization_service import OptimizationService
        svc = OptimizationService()

        with patch("app.graph.nodes.optimization_agent.post_sale_optimization_node") as mock_node:
            mock_node.return_value = {
                "optimization_suggestion": {"new_price": 80000},
                "status": "optimization_suggested",
                "tool_calls": [{"tool_name": "price_opt"}],
            }
            result = svc.run_post_sale_optimization(
                session_id="s1",
                product_data={"confirmed_product": {"brand": "A"}},
                listing_data={"canonical_listing": {"price": 100000}},
                sale_status="unsold",
            )

        assert "optimization_suggestion" in result
        assert "tool_calls" in result
        assert result["optimization_suggestion"]["new_price"] == 80000

    @pytest.mark.unit
    def test_sold_status(self):
        from app.services.optimization_service import OptimizationService
        svc = OptimizationService()

        with patch("app.graph.nodes.optimization_agent.post_sale_optimization_node") as mock_node:
            mock_node.return_value = {
                "optimization_suggestion": None,
                "status": None,
                "tool_calls": [],
            }
            result = svc.run_post_sale_optimization(
                session_id="s1",
                product_data={}, listing_data={},
                sale_status="sold",
            )

        assert result["optimization_suggestion"] is None

    @pytest.mark.unit
    def test_empty_tool_calls_default(self):
        from app.services.optimization_service import OptimizationService
        svc = OptimizationService()

        with patch("app.graph.nodes.optimization_agent.post_sale_optimization_node") as mock_node:
            mock_node.return_value = {}
            result = svc.run_post_sale_optimization(
                session_id="s1",
                product_data={}, listing_data={},
                sale_status="unsold",
            )

        assert result["tool_calls"] == []


# ─────────────────────────────────────────────────────────────────
# recovery_service: run_recovery
# ─────────────────────────────────────────────────────────────────

class TestRecoveryService:

    @pytest.mark.unit
    def test_returns_expected_structure(self):
        from app.services.recovery_service import RecoveryService
        svc = RecoveryService()

        with patch("app.graph.nodes.recovery_agent.recovery_node") as mock_node:
            mock_node.return_value = {
                "publish_diagnostics": [{"platform": "bunjang", "error": "auth"}],
                "tool_calls": [{"tool_name": "diagnose"}],
            }
            result = svc.run_recovery(
                session_id="s1",
                product_data={"confirmed_product": {"brand": "A"}},
                publish_results={"bunjang": {"success": False}},
            )

        assert len(result["publish_diagnostics"]) == 1
        assert len(result["tool_calls"]) == 1

    @pytest.mark.unit
    def test_empty_defaults(self):
        from app.services.recovery_service import RecoveryService
        svc = RecoveryService()

        with patch("app.graph.nodes.recovery_agent.recovery_node") as mock_node:
            mock_node.return_value = {}
            result = svc.run_recovery(
                session_id="s1",
                product_data={},
                publish_results={},
            )

        assert result["publish_diagnostics"] == []
        assert result["tool_calls"] == []


# ─────────────────────────────────────────────────────────────────
# 상태 전이 원자성 통합 검증 (M57 보강)
# ─────────────────────────────────────────────────────────────────

class TestAtomicityIntegration:
    """expected_status가 API 테스트 레벨에서 409를 발생시키는 시나리오."""

    @pytest.mark.unit
    def test_concurrent_double_click_scenario(self):
        """더블클릭 시뮬레이션: 첫 번째는 성공, 두 번째는 409."""
        from app.domain.exceptions import InvalidStateTransitionError

        mock_repo = MagicMock()
        # 첫 호출: 성공, 두 번째: None (expected_status 불일치)
        mock_repo.update.side_effect = [
            {"id": "s1", "status": "publishing"},
            None,
        ]
        mock_repo.get_by_id.return_value = {
            "id": "s1", "status": "awaiting_publish_approval",
            "product_data_jsonb": {}, "listing_data_jsonb": {},
            "workflow_meta_jsonb": {}, "selected_platforms_jsonb": ["bunjang"],
        }

        from app.services.session_service import SessionService
        svc = SessionService(
            session_repository=mock_repo,
            product_service=MagicMock(),
            publish_service=MagicMock(),
            copilot_service=MagicMock(),
            recovery_service=MagicMock(),
            optimization_service=MagicMock(),
        )

        # 첫 번째: 성공
        result = svc._update_or_raise("s1", {"status": "publishing"}, expected_status="awaiting_publish_approval")
        assert result["status"] == "publishing"

        # 두 번째: 409
        with pytest.raises(InvalidStateTransitionError):
            svc._update_or_raise("s1", {"status": "publishing"}, expected_status="awaiting_publish_approval")
