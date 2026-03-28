"""
M56: tool_calls trace 봉합 테스트
M57: 상태 전이 원자성 테스트

CTO3 P0 지적 대응:
- _build_workflow_payload()가 tool_calls 등 agent trace를 보존하는지
- _update_or_raise()가 expected_status 조건으로 TOCTOU를 방어하는지
- session_ui의 agent_trace가 확장 필드를 포함하는지
"""
import pytest
from copy import deepcopy

from app.services.session_ui import build_session_ui_response


# ─────────────────────────────────────────────────────────────────
# M56: tool_calls trace 봉합
# ─────────────────────────────────────────────────────────────────

class TestBuildWorkflowPayloadTrace:
    """_build_workflow_payload가 agent trace 필드를 보존하는지 검증."""

    def _make_service(self):
        from app.services.seller_copilot_service import SellerCopilotService
        return SellerCopilotService()

    @pytest.mark.unit
    def test_tool_calls_preserved(self):
        svc = self._make_service()
        final_state = {
            "tool_calls": [
                {"tool_name": "lc_generate_listing_tool", "success": True},
                {"tool_name": "lc_rewrite_listing_tool", "success": True},
            ],
            "debug_logs": ["log1"],
        }
        result = svc._build_workflow_payload({}, final_state, integration_phase="test")
        assert result["tool_calls"] == final_state["tool_calls"]
        assert len(result["tool_calls"]) == 2

    @pytest.mark.unit
    def test_decision_rationale_preserved(self):
        svc = self._make_service()
        rationale = ["중앙값 850000원 기준 가격 설정"]
        final_state = {"decision_rationale": rationale}
        result = svc._build_workflow_payload({}, final_state, integration_phase="test")
        assert result["decision_rationale"] == rationale

    @pytest.mark.unit
    def test_plan_preserved(self):
        svc = self._make_service()
        plan = {"focus": "빠른 판매", "steps": ["step1", "step2"]}
        final_state = {"plan": plan}
        result = svc._build_workflow_payload({}, final_state, integration_phase="test")
        assert result["plan"] == plan

    @pytest.mark.unit
    def test_critic_fields_preserved(self):
        svc = self._make_service()
        final_state = {
            "critic_score": 85,
            "critic_feedback": [{"type": "title", "impact": "medium"}],
        }
        result = svc._build_workflow_payload({}, final_state, integration_phase="test")
        assert result["critic_score"] == 85
        assert len(result["critic_feedback"]) == 1

    @pytest.mark.unit
    def test_empty_trace_defaults(self):
        svc = self._make_service()
        result = svc._build_workflow_payload({}, {}, integration_phase="test")
        assert result["tool_calls"] == []
        assert result["decision_rationale"] == []
        assert result["plan"] is None
        assert result["critic_score"] is None
        assert result["critic_feedback"] == []

    @pytest.mark.unit
    def test_existing_meta_not_lost(self):
        """기존 workflow_meta 필드가 덮어써지지 않는지 확인."""
        svc = self._make_service()
        existing = {"custom_field": "keep_me", "checkpoint": "old"}
        final_state = {"checkpoint": "new", "tool_calls": [{"tool_name": "t1"}]}
        result = svc._build_workflow_payload(existing, final_state, integration_phase="test")
        assert result["custom_field"] == "keep_me"
        assert result["checkpoint"] == "new"


# ─────────────────────────────────────────────────────────────────
# M56: session_ui agent_trace 확장 검증
# ─────────────────────────────────────────────────────────────────

class TestSessionUiAgentTrace:
    """UI 응답의 agent_trace에 확장 필드가 포함되는지 검증."""

    def _make_session(self, **workflow_overrides):
        wm = {
            "tool_calls": [{"tool_name": "t1", "success": True}],
            "rewrite_history": [],
            "decision_rationale": ["reason1"],
            "plan": {"focus": "test"},
            "critic_score": 90,
            "critic_feedback": [{"type": "price"}],
        }
        wm.update(workflow_overrides)
        return {
            "id": "sess-1",
            "status": "draft_generated",
            "product_data_jsonb": {},
            "listing_data_jsonb": {},
            "workflow_meta_jsonb": wm,
        }

    @pytest.mark.unit
    def test_agent_trace_includes_all_fields(self):
        resp = build_session_ui_response(self._make_session())
        trace = resp["agent_trace"]
        assert len(trace["tool_calls"]) == 1
        assert trace["decision_rationale"] == ["reason1"]
        assert trace["plan"]["focus"] == "test"
        assert trace["critic_score"] == 90
        assert len(trace["critic_feedback"]) == 1

    @pytest.mark.unit
    def test_agent_trace_empty_defaults(self):
        resp = build_session_ui_response(self._make_session(
            tool_calls=None, decision_rationale=None,
            plan=None, critic_score=None, critic_feedback=None,
        ))
        trace = resp["agent_trace"]
        assert trace["tool_calls"] == []
        assert trace["decision_rationale"] == []
        assert trace["plan"] is None
        assert trace["critic_score"] is None
        assert trace["critic_feedback"] == []


# ─────────────────────────────────────────────────────────────────
# M57: 상태 전이 원자성
# ─────────────────────────────────────────────────────────────────

class TestUpdateOrRaiseAtomicity:
    """_update_or_raise가 expected_status 불일치 시 409를 발생시키는지 검증."""

    @pytest.mark.unit
    def test_expected_status_mismatch_raises_transition_error(self):
        """expected_status가 실제와 다르면 InvalidStateTransitionError."""
        from unittest.mock import MagicMock
        from app.domain.exceptions import InvalidStateTransitionError

        mock_repo = MagicMock()
        mock_repo.update.return_value = None  # expected_status 불일치 → None

        from app.services.session_service import SessionService
        svc = SessionService(
            session_repository=mock_repo,
            product_service=MagicMock(),
            publish_orchestrator=MagicMock(),
            copilot_service=MagicMock(),
            sale_tracker=MagicMock(),
        )

        with pytest.raises(InvalidStateTransitionError):
            svc._update_or_raise("sess-1", {"status": "publishing"}, expected_status="draft_generated")

        mock_repo.update.assert_called_once_with(
            session_id="sess-1",
            payload={"status": "publishing"},
            expected_status="draft_generated",
        )

    @pytest.mark.unit
    def test_without_expected_status_raises_update_error(self):
        """expected_status 없이 실패하면 SessionUpdateError."""
        from unittest.mock import MagicMock
        from app.domain.exceptions import SessionUpdateError

        mock_repo = MagicMock()
        mock_repo.update.return_value = None

        from app.services.session_service import SessionService
        svc = SessionService(
            session_repository=mock_repo,
            product_service=MagicMock(),
            publish_orchestrator=MagicMock(),
            copilot_service=MagicMock(),
            sale_tracker=MagicMock(),
        )

        with pytest.raises(SessionUpdateError):
            svc._update_or_raise("sess-1", {"status": "publishing"})

    @pytest.mark.unit
    def test_successful_update_with_expected_status(self):
        """expected_status가 일치하면 정상 반환."""
        from unittest.mock import MagicMock

        mock_repo = MagicMock()
        mock_repo.update.return_value = {"id": "sess-1", "status": "publishing"}

        from app.services.session_service import SessionService
        svc = SessionService(
            session_repository=mock_repo,
            product_service=MagicMock(),
            publish_orchestrator=MagicMock(),
            copilot_service=MagicMock(),
            sale_tracker=MagicMock(),
        )

        result = svc._update_or_raise("sess-1", {"status": "publishing"}, expected_status="draft_generated")
        assert result["status"] == "publishing"


class TestPersistAndRespondAtomicity:
    """_persist_and_respond가 expected_status를 전달하는지 검증."""

    @pytest.mark.unit
    def test_expected_status_forwarded_to_update(self):
        from unittest.mock import MagicMock, patch

        mock_repo = MagicMock()
        mock_repo.update.return_value = {
            "id": "sess-1", "status": "draft_generated",
            "product_data_jsonb": {}, "listing_data_jsonb": {},
            "workflow_meta_jsonb": {},
        }

        from app.services.session_service import SessionService
        svc = SessionService(
            session_repository=mock_repo,
            product_service=MagicMock(),
            publish_orchestrator=MagicMock(),
            copilot_service=MagicMock(),
            sale_tracker=MagicMock(),
        )

        svc._persist_and_respond(
            "sess-1", "draft_generated",
            expected_status="product_confirmed",
        )

        mock_repo.update.assert_called_once()
        call_kwargs = mock_repo.update.call_args
        assert call_kwargs.kwargs.get("expected_status") == "product_confirmed" or \
               call_kwargs[1].get("expected_status") == "product_confirmed" or \
               (len(call_kwargs[0]) >= 3 and call_kwargs[0][2] == "product_confirmed")
