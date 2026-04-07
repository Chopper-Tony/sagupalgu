"""
M95: 에러 복구 E2E 시나리오 테스트

게시 실패 → recovery 진단 → 재시도 → Discord 알림까지의 전체 흐름을 검증.
모든 외부 서비스(publisher, LLM, Discord)는 mock 처리.
동기 게시 모드(PUBLISH_USE_QUEUE=False)로 테스트하여 DB 의존성 격리.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.domain.publish_policy import (
    DISCORD_ALERT_THRESHOLD,
    FAILURE_TAXONOMY,
    classify_error,
)
from app.services.publish_service import PublishService
from app.services.publish_orchestrator import PublishOrchestrator
from app.services.recovery_service import RecoveryService
from app.services.sale_tracker import SaleTracker
from app.services.session_service import SessionService


# Queue 경로가 아닌 동기 실행 경로로 테스트 (DB 의존성 격리)
pytestmark = pytest.mark.usefixtures("_force_sync_publish")


@pytest.fixture(autouse=True)
def _force_sync_publish():
    """PUBLISH_USE_QUEUE=False로 강제하여 동기 게시 경로를 사용."""
    with patch("app.core.config.get_settings") as mock_gs:
        mock_gs.return_value.publish_use_queue = False
        yield


# ── 헬퍼 ──────────────────────────────────────────────────────────


def _make_session_service(
    session_record: dict,
    publish_results: tuple | None = None,
) -> SessionService:
    """SessionService를 mock 의존성으로 구성한다."""
    repo = MagicMock()
    repo.get_by_id.return_value = session_record
    repo.update.side_effect = lambda session_id, payload, **kw: {
        **session_record,
        **payload,
    }

    publish_svc = AsyncMock(spec=PublishService)
    if publish_results is not None:
        publish_svc.execute_publish.return_value = publish_results

    recovery_svc = MagicMock(spec=RecoveryService)
    recovery_svc.run_recovery.return_value = {
        "publish_diagnostics": [
            {"platform": "bunjang", "error_code": "timeout", "likely_cause": "서버 응답 지연"}
        ],
        "tool_calls": [{"tool_name": "diagnose_publish_failure_tool", "success": True}],
    }

    publish_orchestrator = PublishOrchestrator(
        session_repository=repo,
        publish_service=publish_svc,
        recovery_service=recovery_svc,
    )

    sale_tracker = MagicMock(spec=SaleTracker)

    svc = SessionService(
        session_repository=repo,
        product_service=MagicMock(),
        publish_orchestrator=publish_orchestrator,
        copilot_service=MagicMock(),
        sale_tracker=sale_tracker,
    )
    return svc


def _make_publish_ready_session(**overrides) -> dict:
    """게시 준비 완료 상태의 세션 레코드를 생성한다."""
    base = {
        "id": "sess-recovery-001",
        "status": "awaiting_publish_approval",
        "selected_platforms_jsonb": ["bunjang"],
        "product_data_jsonb": {
            "image_paths": ["/img/test.jpg"],
            "confirmed_product": {
                "brand": "Apple",
                "model": "iPhone 15 Pro",
                "category": "smartphone",
            },
        },
        "listing_data_jsonb": {
            "canonical_listing": {
                "title": "iPhone 15 Pro 판매",
                "description": "깨끗하게 사용했습니다.",
                "price": 950000,
                "tags": ["iPhone"],
                "images": ["/img/test.jpg"],
            },
            "platform_packages": {
                "bunjang": {
                    "title": "iPhone 15 Pro 판매",
                    "body": "깨끗하게 사용했습니다.",
                    "price": 983000,
                    "images": ["/img/test.jpg"],
                },
            },
        },
        "workflow_meta_jsonb": {
            "checkpoint": "C_prepared",
            "tool_calls": [],
            "publish_retry_count": 0,
        },
    }
    base.update(overrides)
    return base


# ── 테스트 ────────────────────────────────────────────────────────


class TestPublishFailureRecovery:
    """게시 실패 → recovery 진단 시나리오"""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_게시_1차실패_후_recovery_진단(self):
        """게시 1차 실패 시 recovery_service.run_recovery가 호출되고
        진단 결과(publish_diagnostics)가 workflow_meta에 기록되는지 확인."""
        session = _make_publish_ready_session()
        fail_results = {
            "bunjang": {
                "success": False,
                "platform": "bunjang",
                "error_code": "timeout",
                "error_message": "번개장터 게시 180초 타임아웃 초과",
                "auto_recoverable": True,
            },
        }

        svc = _make_session_service(
            session_record=session,
            publish_results=(fail_results, True),
        )

        result = await svc.publish_session("sess-recovery-001")

        # recovery_service.run_recovery 호출 확인 (PublishOrchestrator 내부)
        svc.publish_orchestrator.recovery_service.run_recovery.assert_called_once()
        call_kwargs = svc.publish_orchestrator.recovery_service.run_recovery.call_args
        assert call_kwargs.kwargs["session_id"] == "sess-recovery-001"
        assert call_kwargs.kwargs["publish_results"] == fail_results

        # 최종 상태가 publishing_failed
        assert result["status"] == "publishing_failed"

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_게시_재시도_성공(self):
        """1차 실패 후 재시도(prepare_publish → publish)에서 성공하는 시나리오.
        publishing_failed → awaiting_publish_approval 전이 후 재게시."""
        # 1차: 실패
        session_failed = _make_publish_ready_session(
            status="awaiting_publish_approval",
        )
        fail_results = {
            "bunjang": {
                "success": False,
                "platform": "bunjang",
                "error_code": "timeout",
                "error_message": "타임아웃",
                "auto_recoverable": True,
            },
        }
        svc = _make_session_service(
            session_record=session_failed,
            publish_results=(fail_results, True),
        )
        result1 = await svc.publish_session("sess-recovery-001")
        assert result1["status"] == "publishing_failed"

        # 2차: 성공 — 세션 상태를 publishing_failed → awaiting_publish_approval로 전이
        session_retry = _make_publish_ready_session(
            status="awaiting_publish_approval",
        )
        success_results = {
            "bunjang": {
                "success": True,
                "platform": "bunjang",
                "external_listing_id": "ext-123",
                "external_url": "https://bunjang.co.kr/products/ext-123",
                "error_code": None,
                "error_message": None,
                "auto_recoverable": None,
            },
        }
        svc2 = _make_session_service(
            session_record=session_retry,
            publish_results=(success_results, False),
        )
        result2 = await svc2.publish_session("sess-recovery-001")
        assert result2["status"] == "completed"

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_3회연속_실패시_discord_alert(self):
        """누적 실패 횟수가 DISCORD_ALERT_THRESHOLD(3) 이상이면
        _send_discord_alert가 호출된다."""
        # 이미 2회 실패한 상태 (publish_retry_count=2)
        session = _make_publish_ready_session()
        session["workflow_meta_jsonb"]["publish_retry_count"] = DISCORD_ALERT_THRESHOLD - 1

        fail_results = {
            "bunjang": {
                "success": False,
                "platform": "bunjang",
                "error_code": "network_error",
                "error_message": "네트워크 연결 오류",
                "auto_recoverable": True,
            },
        }
        svc = _make_session_service(
            session_record=session,
            publish_results=(fail_results, True),
        )

        with patch.object(svc.publish_orchestrator, "_send_discord_alert", new_callable=AsyncMock) as mock_alert:
            await svc.publish_session("sess-recovery-001")

            # 3회째이므로 Discord 알림 발송
            mock_alert.assert_called_once()
            call_kwargs = mock_alert.call_args.kwargs
            assert "sess-recovery-001" in call_kwargs["session_id"]
            assert "3회" in call_kwargs["message"]

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_2회실패시_discord_미발송(self):
        """누적 실패 횟수가 임계값 미만이면 Discord 알림이 발송되지 않는다."""
        session = _make_publish_ready_session()
        session["workflow_meta_jsonb"]["publish_retry_count"] = 0  # 첫 실패

        fail_results = {
            "bunjang": {
                "success": False,
                "platform": "bunjang",
                "error_code": "timeout",
                "error_message": "타임아웃",
                "auto_recoverable": True,
            },
        }
        svc = _make_session_service(
            session_record=session,
            publish_results=(fail_results, True),
        )

        with patch.object(svc.publish_orchestrator, "_send_discord_alert", new_callable=AsyncMock) as mock_alert:
            await svc.publish_session("sess-recovery-001")
            # 1회째이므로 Discord 알림 미발송
            mock_alert.assert_not_called()


class TestPublishErrorClassification:
    """publish_policy.classify_error 에러 분류 테스트"""

    @pytest.mark.integration
    def test_publish_timeout_분류(self):
        """타임아웃 에러가 timeout으로 분류되고 auto_recoverable=True."""
        result = classify_error("timeout")
        assert result["error_code"] == "timeout"
        assert result["category"] == "network"
        assert result["auto_recoverable"] is True

    @pytest.mark.integration
    def test_timeout_메시지_기반_추론(self):
        """에러 코드가 없어도 메시지에 'timed out'이 포함되면 timeout 분류."""
        result = classify_error("unknown", "Request timed out after 180s")
        assert result["error_code"] == "timeout"
        assert result["auto_recoverable"] is True

    @pytest.mark.integration
    def test_auto_recoverable_판정_network(self):
        """네트워크 에러는 auto_recoverable=True."""
        result = classify_error("network_error")
        assert result["auto_recoverable"] is True

    @pytest.mark.integration
    def test_auto_recoverable_판정_login(self):
        """로그인 만료는 auto_recoverable=False (수동 갱신 필요)."""
        result = classify_error("login_expired")
        assert result["auto_recoverable"] is False

    @pytest.mark.integration
    def test_auto_recoverable_판정_content_policy(self):
        """콘텐츠 정책 위반은 auto_recoverable=False."""
        result = classify_error("content_policy")
        assert result["auto_recoverable"] is False

    @pytest.mark.integration
    def test_unknown_에러코드_fallback(self):
        """알 수 없는 에러 코드는 publish_exception으로 분류."""
        result = classify_error("some_random_error", "알 수 없는 에러")
        assert result["error_code"] == "publish_exception"
        assert result["auto_recoverable"] is False

    @pytest.mark.integration
    def test_image_upload_failed_분류(self):
        """이미지 업로드 실패 에러 분류."""
        result = classify_error("image_upload_failed")
        assert result["error_code"] == "image_upload_failed"
        assert result["auto_recoverable"] is True

    @pytest.mark.integration
    def test_category_selection_failed_분류(self):
        """카테고리 선택 실패 에러 분류."""
        result = classify_error("category_selection_failed")
        assert result["auto_recoverable"] is True


class TestRecoveryNodeDiagnosis:
    """recovery_service.run_recovery 진단 결과 테스트"""

    @pytest.mark.integration
    def test_recovery_node_진단_결과(self):
        """recovery_node가 publish_diagnostics를 반환하는지 확인.
        recovery_node 내부 LLM/tool은 mock 처리."""
        from app.graph.nodes.recovery_agent import recovery_node

        # recovery_node에서 사용하는 tool들을 mock
        mock_diag = {
            "tool_name": "diagnose_publish_failure_tool",
            "output": {
                "platform": "bunjang",
                "error_code": "timeout",
                "likely_cause": "서버 응답 지연",
                "auto_recoverable": True,
            },
            "success": True,
        }
        mock_patch = {
            "tool_name": "auto_patch_tool",
            "output": {
                "type": "retry",
                "auto_executable": True,
                "description": "타임아웃 — 재시도 가능",
            },
            "success": True,
        }

        state = {
            "session_id": "sess-diag-001",
            "status": "publishing_failed",
            "image_paths": ["/img/test.jpg"],
            "publish_results": {
                "bunjang": {
                    "success": False,
                    "error_code": "timeout",
                    "error_message": "게시 타임아웃 초과",
                },
            },
            "confirmed_product": {"brand": "Apple", "model": "iPhone 15 Pro"},
            "canonical_listing": {"title": "iPhone 15 Pro 판매", "description": "테스트"},
            "tool_calls": [],
            "error_history": [],
            "debug_logs": [],
            "publish_retry_count": 0,
            "patch_suggestions": [],
        }

        # ReAct 경로를 강제 실패시켜 fallback 경로로 보냄
        # fallback에서 lazy import되는 도구들을 mock
        mock_diag_fn = MagicMock(return_value=mock_diag)
        mock_patch_fn = MagicMock(return_value=mock_patch)
        mock_discord_fn = MagicMock(
            return_value={"tool_name": "discord_alert_tool", "success": True},
        )

        with patch(
            "app.graph.nodes.recovery_agent._build_react_llm",
            side_effect=ValueError("LLM 없음 — 강제 fallback"),
        ), patch(
            "app.graph.nodes.recovery_agent._run_async",
            side_effect=lambda fn: fn() if callable(fn) else fn,
        ), patch(
            "app.tools.agentic_tools.diagnose_publish_failure_tool",
            mock_diag_fn,
        ), patch(
            "app.tools.agentic_tools.auto_patch_tool",
            mock_patch_fn,
        ), patch(
            "app.tools.agentic_tools.discord_alert_tool",
            mock_discord_fn,
        ):
            result_state = recovery_node(state)

        # fallback에서 diagnose → auto_recoverable=True → should_retry_publish=True
        assert result_state.get("should_retry_publish") is True
        assert result_state.get("patch_suggestions") is not None
        assert len(result_state["patch_suggestions"]) > 0
        assert result_state["tool_calls"]  # tool_calls가 기록됨

    @pytest.mark.integration
    def test_recovery_node_실패없으면_스킵(self):
        """실패한 플랫폼이 없으면 recovery를 스킵한다."""
        from app.graph.nodes.recovery_agent import recovery_node

        state = {
            "session_id": "sess-diag-002",
            "status": "completed",
            "image_paths": [],
            "publish_results": {
                "bunjang": {"success": True},
            },
            "confirmed_product": {},
            "canonical_listing": {},
            "tool_calls": [],
            "error_history": [],
            "debug_logs": [],
            "publish_retry_count": 0,
        }

        result_state = recovery_node(state)
        assert result_state.get("should_retry_publish") is False
        assert result_state.get("checkpoint") == "D_complete"
