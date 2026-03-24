"""
상태 전이 계약 + UI 응답 shape 검증 테스트.

1. 모든 SessionStatus가 ALLOWED_TRANSITIONS에 키로 존재
2. 전이 대상도 유효한 SessionStatus
3. resolve_next_action이 모든 상태에 대해 정의
4. build_session_ui_response 출력 shape가 SessionUIResponse 스키마와 일치
5. 터미널 상태가 올바르게 정의
"""
import pytest

from app.domain.session_status import (
    ALLOWED_TRANSITIONS,
    TERMINAL_STATUSES,
    assert_allowed_transition,
    is_terminal_status,
    resolve_next_action,
)
from app.schemas.session import SessionUIResponse
from app.services.session_ui import build_session_ui_response

# SessionStatus에 정의된 모든 상태
ALL_STATUSES = list(ALLOWED_TRANSITIONS.keys())


class TestAllowedTransitionsCompleteness:
    """ALLOWED_TRANSITIONS가 모든 상태를 빠짐없이 커버하는지 검증."""

    @pytest.mark.unit
    def test_all_statuses_have_transition_entry(self):
        """모든 상태가 ALLOWED_TRANSITIONS에 키로 존재해야 한다."""
        expected = {
            "session_created", "images_uploaded", "awaiting_product_confirmation",
            "product_confirmed", "market_analyzing", "draft_generated",
            "awaiting_publish_approval", "publishing", "completed",
            "failed", "publishing_failed", "awaiting_sale_status_update",
            "optimization_suggested",
        }
        assert set(ALLOWED_TRANSITIONS.keys()) == expected

    @pytest.mark.unit
    def test_all_transition_targets_are_valid_statuses(self):
        """전이 대상도 유효한 상태여야 한다."""
        all_keys = set(ALLOWED_TRANSITIONS.keys())
        for source, targets in ALLOWED_TRANSITIONS.items():
            for target in targets:
                assert target in all_keys, (
                    f"'{source}' → '{target}': target이 유효한 상태가 아닙니다"
                )

    @pytest.mark.unit
    def test_no_self_loops_except_allowed(self):
        """self-loop가 허용되는 상태는 명시적으로 정의된 것만."""
        self_loop_allowed = {"draft_generated", "awaiting_sale_status_update"}
        for status, targets in ALLOWED_TRANSITIONS.items():
            if status in targets:
                assert status in self_loop_allowed, (
                    f"'{status}'에 예상치 못한 self-loop이 있습니다"
                )


class TestTerminalStatuses:

    @pytest.mark.unit
    def test_terminal_statuses_have_no_or_limited_transitions(self):
        """터미널 상태는 전이가 없거나 매우 제한적이어야 한다."""
        for status in TERMINAL_STATUSES:
            targets = ALLOWED_TRANSITIONS.get(status, [])
            assert len(targets) <= 1, (
                f"터미널 상태 '{status}'의 전이가 너무 많습니다: {targets}"
            )

    @pytest.mark.unit
    def test_is_terminal_status_matches_set(self):
        for status in ALL_STATUSES:
            expected = status in TERMINAL_STATUSES
            assert is_terminal_status(status) == expected


class TestResolveNextAction:
    """resolve_next_action이 모든 비터미널 상태에 대해 값을 반환하는지."""

    @pytest.mark.unit
    def test_all_non_terminal_statuses_have_next_action(self):
        for status in ALL_STATUSES:
            if status in TERMINAL_STATUSES:
                continue
            if status == "market_analyzing":
                # 내부 상태 — UI가 직접 호출하지 않음
                continue
            action = resolve_next_action(status)
            assert action is not None, (
                f"상태 '{status}'에 대한 next_action이 None입니다"
            )

    @pytest.mark.unit
    def test_awaiting_confirmation_respects_needs_input(self):
        assert resolve_next_action("awaiting_product_confirmation", needs_user_input=True) == "provide_product_info"
        assert resolve_next_action("awaiting_product_confirmation", needs_user_input=False) == "confirm_product"


class TestAssertAllowedTransition:

    @pytest.mark.unit
    def test_valid_transition_passes(self):
        # session_created → images_uploaded는 허용
        assert_allowed_transition("session_created", "images_uploaded")

    @pytest.mark.unit
    def test_invalid_transition_raises(self):
        from app.domain.exceptions import InvalidStateTransitionError
        with pytest.raises(InvalidStateTransitionError):
            assert_allowed_transition("session_created", "completed")

    @pytest.mark.unit
    def test_full_happy_path_chain(self):
        """전체 정상 플로우 체인이 유효한지 검증."""
        chain = [
            "session_created",
            "images_uploaded",
            "awaiting_product_confirmation",
            "product_confirmed",
            "draft_generated",
            "awaiting_publish_approval",
            "publishing",
            "completed",
        ]
        for i in range(len(chain) - 1):
            assert_allowed_transition(chain[i], chain[i + 1])


class TestBuildSessionUIResponseShape:
    """build_session_ui_response 출력이 SessionUIResponse 스키마와 호환되는지."""

    @pytest.mark.unit
    def test_minimal_record_produces_valid_response(self):
        record = {
            "id": "sess-test",
            "status": "session_created",
            "product_data_jsonb": {},
            "listing_data_jsonb": {},
            "workflow_meta_jsonb": {},
            "selected_platforms_jsonb": [],
        }
        result = build_session_ui_response(record)
        # SessionUIResponse로 파싱 가능해야 한다
        parsed = SessionUIResponse(**result)
        assert parsed.session_id == "sess-test"
        assert parsed.status == "session_created"
        assert parsed.next_action == "upload_images"

    @pytest.mark.unit
    def test_all_statuses_produce_parseable_response(self):
        """모든 상태에 대해 SessionUIResponse 파싱이 가능해야 한다."""
        for status in ALL_STATUSES:
            record = {
                "id": f"sess-{status}",
                "status": status,
                "product_data_jsonb": {},
                "listing_data_jsonb": {},
                "workflow_meta_jsonb": {},
                "selected_platforms_jsonb": [],
            }
            result = build_session_ui_response(record)
            parsed = SessionUIResponse(**result)
            assert parsed.status == status

    @pytest.mark.unit
    def test_response_contains_all_required_sections(self):
        record = {
            "id": "sess-test",
            "status": "draft_generated",
            "product_data_jsonb": {"confirmed_product": {"model": "S24"}},
            "listing_data_jsonb": {"canonical_listing": {"title": "테스트"}},
            "workflow_meta_jsonb": {"tool_calls": [{"tool_name": "test"}]},
            "selected_platforms_jsonb": ["bunjang"],
        }
        result = build_session_ui_response(record)
        assert "product" in result
        assert "listing" in result
        assert "publish" in result
        assert "agent_trace" in result
        assert "debug" in result

    @pytest.mark.unit
    def test_response_image_count_field(self):
        """product 섹션에 image_paths가 포함되어야 한다."""
        record = {
            "id": "sess-test",
            "status": "images_uploaded",
            "product_data_jsonb": {"image_paths": ["img1.jpg", "img2.jpg"]},
            "listing_data_jsonb": {},
            "workflow_meta_jsonb": {},
            "selected_platforms_jsonb": [],
        }
        result = build_session_ui_response(record)
        assert result["product"]["image_paths"] == ["img1.jpg", "img2.jpg"]
