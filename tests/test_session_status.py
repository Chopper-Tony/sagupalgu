"""
세션 상태 머신 계약 테스트 (순수 단위)

외부 의존성 없음. session_status.py의 모든 규칙을 코드로 잠근다.
- 허용 전이 / 차단 전이
- 터미널 상태 판별
- resolve_next_action 매핑
"""
import pytest

from app.domain.session_status import (
    ALLOWED_TRANSITIONS,
    TERMINAL_STATUSES,
    assert_allowed_transition,
    is_terminal_status,
    resolve_next_action,
)


# ─────────────────────────────────────────────────────────────────
# 허용 전이
# ─────────────────────────────────────────────────────────────────

class TestAllowedTransitions:

    @pytest.mark.unit
    def test_session_created_to_images_uploaded(self):
        assert_allowed_transition("session_created", "images_uploaded")

    @pytest.mark.unit
    def test_images_uploaded_to_awaiting_product_confirmation(self):
        assert_allowed_transition("images_uploaded", "awaiting_product_confirmation")

    @pytest.mark.unit
    def test_awaiting_product_confirmation_to_product_confirmed(self):
        assert_allowed_transition("awaiting_product_confirmation", "product_confirmed")

    @pytest.mark.unit
    def test_product_confirmed_to_draft_generated(self):
        assert_allowed_transition("product_confirmed", "draft_generated")

    @pytest.mark.unit
    def test_product_confirmed_to_market_analyzing(self):
        assert_allowed_transition("product_confirmed", "market_analyzing")

    @pytest.mark.unit
    def test_market_analyzing_to_draft_generated(self):
        assert_allowed_transition("market_analyzing", "draft_generated")

    @pytest.mark.unit
    def test_draft_generated_to_awaiting_publish_approval(self):
        assert_allowed_transition("draft_generated", "awaiting_publish_approval")

    @pytest.mark.unit
    def test_draft_generated_to_draft_generated(self):
        """재작성은 draft_generated → draft_generated 자기 전이 허용"""
        assert_allowed_transition("draft_generated", "draft_generated")

    @pytest.mark.unit
    def test_awaiting_publish_approval_to_publishing(self):
        assert_allowed_transition("awaiting_publish_approval", "publishing")

    @pytest.mark.unit
    def test_publishing_to_completed(self):
        assert_allowed_transition("publishing", "completed")

    @pytest.mark.unit
    def test_publishing_to_publishing_failed(self):
        assert_allowed_transition("publishing", "publishing_failed")

    @pytest.mark.unit
    def test_completed_to_awaiting_sale_status_update(self):
        assert_allowed_transition("completed", "awaiting_sale_status_update")

    @pytest.mark.unit
    def test_awaiting_sale_status_update_to_optimization_suggested(self):
        assert_allowed_transition("awaiting_sale_status_update", "optimization_suggested")

    @pytest.mark.unit
    def test_awaiting_sale_status_update_to_itself(self):
        assert_allowed_transition("awaiting_sale_status_update", "awaiting_sale_status_update")

    @pytest.mark.unit
    def test_publishing_failed_to_awaiting_publish_approval(self):
        assert_allowed_transition("publishing_failed", "awaiting_publish_approval")

    @pytest.mark.unit
    def test_market_analyzing_to_failed(self):
        assert_allowed_transition("market_analyzing", "failed")


# ─────────────────────────────────────────────────────────────────
# 차단 전이
# ─────────────────────────────────────────────────────────────────

class TestBlockedTransitions:

    @pytest.mark.unit
    def test_session_created_cannot_skip_to_draft(self):
        with pytest.raises(ValueError, match="허용되지 않은 상태 전이"):
            assert_allowed_transition("session_created", "draft_generated")

    @pytest.mark.unit
    def test_completed_cannot_go_back_to_publishing(self):
        with pytest.raises(ValueError):
            assert_allowed_transition("completed", "publishing")

    @pytest.mark.unit
    def test_optimization_suggested_is_terminal(self):
        with pytest.raises(ValueError):
            assert_allowed_transition("optimization_suggested", "draft_generated")

    @pytest.mark.unit
    def test_failed_is_terminal(self):
        with pytest.raises(ValueError):
            assert_allowed_transition("failed", "session_created")

    @pytest.mark.unit
    def test_unknown_status_raises(self):
        with pytest.raises(ValueError):
            assert_allowed_transition("nonexistent_status", "images_uploaded")

    @pytest.mark.unit
    def test_error_message_contains_current_and_next(self):
        with pytest.raises(ValueError) as exc_info:
            assert_allowed_transition("session_created", "completed")
        msg = str(exc_info.value)
        assert "session_created" in msg
        assert "completed" in msg

    @pytest.mark.unit
    def test_error_message_contains_allowed_list(self):
        with pytest.raises(ValueError) as exc_info:
            assert_allowed_transition("session_created", "completed")
        msg = str(exc_info.value)
        assert "images_uploaded" in msg  # allowed에 images_uploaded가 있어야 함


# ─────────────────────────────────────────────────────────────────
# 터미널 상태
# ─────────────────────────────────────────────────────────────────

class TestTerminalStatus:

    @pytest.mark.unit
    def test_completed_is_terminal(self):
        assert is_terminal_status("completed") is True

    @pytest.mark.unit
    def test_failed_is_terminal(self):
        assert is_terminal_status("failed") is True

    @pytest.mark.unit
    def test_publishing_failed_is_terminal(self):
        assert is_terminal_status("publishing_failed") is True

    @pytest.mark.unit
    def test_optimization_suggested_is_terminal(self):
        assert is_terminal_status("optimization_suggested") is True

    @pytest.mark.unit
    def test_session_created_is_not_terminal(self):
        assert is_terminal_status("session_created") is False

    @pytest.mark.unit
    def test_draft_generated_is_not_terminal(self):
        assert is_terminal_status("draft_generated") is False

    @pytest.mark.unit
    def test_publishing_is_not_terminal(self):
        assert is_terminal_status("publishing") is False

    @pytest.mark.unit
    def test_truly_terminal_statuses_have_no_allowed_transitions(self):
        """failed / optimization_suggested는 전이가 완전히 막혀 있어야 한다.
        (completed / publishing_failed는 후속 플로우가 있어 전이 존재)
        """
        truly_terminal = {"failed", "optimization_suggested"}
        for status in truly_terminal:
            allowed = ALLOWED_TRANSITIONS.get(status, [])
            assert allowed == [], f"{status} should have no allowed transitions"


# ─────────────────────────────────────────────────────────────────
# resolve_next_action 매핑
# ─────────────────────────────────────────────────────────────────

class TestResolveNextAction:

    @pytest.mark.unit
    def test_session_created(self):
        assert resolve_next_action("session_created") == "upload_images"

    @pytest.mark.unit
    def test_images_uploaded(self):
        assert resolve_next_action("images_uploaded") == "analyze"

    @pytest.mark.unit
    def test_product_confirmed(self):
        assert resolve_next_action("product_confirmed") == "generate_listing"

    @pytest.mark.unit
    def test_draft_generated(self):
        assert resolve_next_action("draft_generated") == "prepare_publish"

    @pytest.mark.unit
    def test_awaiting_publish_approval(self):
        assert resolve_next_action("awaiting_publish_approval") == "publish"

    @pytest.mark.unit
    def test_publishing(self):
        assert resolve_next_action("publishing") == "poll_status"

    @pytest.mark.unit
    def test_completed(self):
        assert resolve_next_action("completed") == "done"

    @pytest.mark.unit
    def test_publishing_failed(self):
        assert resolve_next_action("publishing_failed") == "retry_or_edit"

    @pytest.mark.unit
    def test_awaiting_sale_status_update(self):
        assert resolve_next_action("awaiting_sale_status_update") == "update_sale_status"

    @pytest.mark.unit
    def test_optimization_suggested(self):
        assert resolve_next_action("optimization_suggested") == "review_optimization"

    @pytest.mark.unit
    def test_awaiting_product_confirmation_without_user_input(self):
        assert resolve_next_action("awaiting_product_confirmation", needs_user_input=False) == "confirm_product"

    @pytest.mark.unit
    def test_awaiting_product_confirmation_with_user_input(self):
        assert resolve_next_action("awaiting_product_confirmation", needs_user_input=True) == "provide_product_info"

    @pytest.mark.unit
    def test_unknown_status_returns_none(self):
        assert resolve_next_action("nonexistent_status") is None
