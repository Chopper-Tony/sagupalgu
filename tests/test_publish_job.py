"""
Publish Job Queue 테스트.

도메인 모델, 상태 전이, 워커 로직 검증.
"""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
import asyncio

from app.domain.publish_job import (
    PublishJobStatus,
    ALLOWED_JOB_TRANSITIONS,
    TERMINAL_STATUSES,
    STEP_TIMEOUTS,
    DEFAULT_MAX_ATTEMPTS,
    WORKER_POLL_INTERVAL_SECONDS,
    WORKER_LOCK_TIMEOUT_SECONDS,
)


# ── 도메인 모델 테스트 ─────────��─────────────────────────────────────

class TestPublishJobStatus:
    def test_all_statuses_defined(self):
        assert len(PublishJobStatus) == 7

    def test_terminal_statuses(self):
        for status in TERMINAL_STATUSES:
            assert ALLOWED_JOB_TRANSITIONS[status] == set()

    def test_pending_can_transition_to_claimed(self):
        assert PublishJobStatus.CLAIMED in ALLOWED_JOB_TRANSITIONS[PublishJobStatus.PENDING]

    def test_running_can_transition_to_completed_or_failed(self):
        allowed = ALLOWED_JOB_TRANSITIONS[PublishJobStatus.RUNNING]
        assert PublishJobStatus.COMPLETED in allowed
        assert PublishJobStatus.FAILED in allowed
        assert PublishJobStatus.RETRY_SCHEDULED in allowed

    def test_retry_scheduled_returns_to_pending(self):
        allowed = ALLOWED_JOB_TRANSITIONS[PublishJobStatus.RETRY_SCHEDULED]
        assert PublishJobStatus.PENDING in allowed

    def test_no_self_transitions(self):
        for status, targets in ALLOWED_JOB_TRANSITIONS.items():
            assert status not in targets

    def test_all_statuses_have_transition_rules(self):
        for status in PublishJobStatus:
            assert status in ALLOWED_JOB_TRANSITIONS


class TestStepTimeouts:
    def test_all_steps_defined(self):
        required = {"login_check", "image_upload", "form_fill", "category_select", "submit", "verify", "total"}
        assert required.issubset(set(STEP_TIMEOUTS.keys()))

    def test_total_is_largest(self):
        total = STEP_TIMEOUTS["total"]
        for step, timeout in STEP_TIMEOUTS.items():
            if step != "total":
                assert timeout < total

    def test_all_positive(self):
        for step, timeout in STEP_TIMEOUTS.items():
            assert timeout > 0


class TestConstants:
    def test_default_max_attempts(self):
        assert DEFAULT_MAX_ATTEMPTS == 3

    def test_poll_interval_reasonable(self):
        assert 1.0 <= WORKER_POLL_INTERVAL_SECONDS <= 10.0

    def test_lock_timeout_reasonable(self):
        assert WORKER_LOCK_TIMEOUT_SECONDS >= STEP_TIMEOUTS["total"]


# ── Repository mock 테스트 ─────��──────────────────────────────────

class TestPublishJobRepository:
    """Repository 메서드 시그니처 및 기본 로직 검증."""

    def test_import(self):
        from app.db.publish_job_repository import PublishJobRepository
        repo = PublishJobRepository()
        assert repo is not None

    def test_create_builds_correct_row(self):
        from app.db.publish_job_repository import PublishJobRepository
        repo = PublishJobRepository()

        mock_client = MagicMock()
        mock_client.table.return_value.insert.return_value.execute.return_value = MagicMock(
            data=[{"id": "test-id", "status": "pending"}]
        )
        repo._get_client = lambda: mock_client

        result = repo.create(
            session_id="sess-1",
            user_id="user-1",
            platform="bunjang",
            payload={"title": "test"},
        )
        assert result["status"] == "pending"

    def test_create_batch_creates_multiple(self):
        from app.db.publish_job_repository import PublishJobRepository
        repo = PublishJobRepository()

        call_count = 0
        def mock_create(**kwargs):
            nonlocal call_count
            call_count += 1
            return {"id": f"job-{call_count}", "platform": kwargs["platform"]}

        repo.create = mock_create
        jobs = repo.create_batch(
            session_id="sess-1",
            user_id="user-1",
            platforms=["bunjang", "joongna"],
            packages={"bunjang": {}, "joongna": {}},
        )
        assert len(jobs) == 2
        assert call_count == 2

    def test_claim_returns_false_on_exception(self):
        from app.db.publish_job_repository import PublishJobRepository
        repo = PublishJobRepository()

        mock_client = MagicMock()
        mock_client.table.return_value.update.return_value.eq.return_value.in_.return_value.execute.side_effect = Exception("unique constraint")
        repo._get_client = lambda: mock_client

        result = repo.claim("job-1", "worker-1")
        assert result is False

    def test_fail_with_auto_recoverable_schedules_retry(self):
        from app.db.publish_job_repository import PublishJobRepository
        repo = PublishJobRepository()

        repo.get_by_id = lambda _: {
            "id": "job-1",
            "attempt_count": 0,
            "max_attempts": 3,
        }
        mock_client = MagicMock()
        mock_client.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[{}])
        repo._get_client = lambda: mock_client

        repo.fail(
            "job-1",
            error_code="timeout",
            error_message="timeout",
            auto_recoverable=True,
        )

        call_args = mock_client.table.return_value.update.call_args[0][0]
        assert call_args["status"] == PublishJobStatus.RETRY_SCHEDULED

    def test_fail_without_auto_recoverable_sets_failed(self):
        from app.db.publish_job_repository import PublishJobRepository
        repo = PublishJobRepository()

        repo.get_by_id = lambda _: {
            "id": "job-1",
            "attempt_count": 0,
            "max_attempts": 3,
        }
        mock_client = MagicMock()
        mock_client.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[{}])
        repo._get_client = lambda: mock_client

        repo.fail(
            "job-1",
            error_code="login_expired",
            error_message="session expired",
            auto_recoverable=False,
        )

        call_args = mock_client.table.return_value.update.call_args[0][0]
        assert call_args["status"] == PublishJobStatus.FAILED

    def test_fail_max_attempts_reached(self):
        from app.db.publish_job_repository import PublishJobRepository
        repo = PublishJobRepository()

        repo.get_by_id = lambda _: {
            "id": "job-1",
            "attempt_count": 2,  # 이미 2회 시도
            "max_attempts": 3,
        }
        mock_client = MagicMock()
        mock_client.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[{}])
        repo._get_client = lambda: mock_client

        repo.fail(
            "job-1",
            error_code="timeout",
            error_message="timeout",
            auto_recoverable=True,  # recoverable이지만 max_attempts 도달
        )

        call_args = mock_client.table.return_value.update.call_args[0][0]
        assert call_args["status"] == PublishJobStatus.FAILED

    def test_cancel_non_terminal(self):
        from app.db.publish_job_repository import PublishJobRepository
        repo = PublishJobRepository()

        mock_client = MagicMock()
        mock_client.table.return_value.update.return_value.eq.return_value.not_.return_value.in_.return_value.execute.return_value = MagicMock(data=[{"id": "job-1"}])
        repo._get_client = lambda: mock_client

        result = repo.cancel("job-1")
        assert result is True


# ── Admin 라��터 테스트 ──────────────���────────────────────────────

class TestAdminRouter:
    def test_import(self):
        from app.api.admin_router import router
        assert router is not None

    def test_routes_registered(self):
        from app.api.admin_router import router
        paths = [r.path for r in router.routes]
        assert "/admin/publish-queue/stats" in paths
        assert "/admin/publish-queue/jobs" in paths
        assert "/admin/publish-queue/release-stuck" in paths


# ── Orchestrator 큐 등록 테스트 ────��──────────────────────────────

class TestPublishOrchestratorQueue:
    def test_publish_via_queue_enqueues_jobs(self):
        """_publish_via_queue를 직접 호출하여 큐 등록 로직 검증."""
        from app.services.publish_orchestrator import PublishOrchestrator

        mock_repo = MagicMock()
        mock_repo.get_by_id.return_value = {"id": "sess-1", "status": "publishing"}
        mock_repo.update.return_value = {"id": "sess-1", "status": "publishing"}

        mock_publish_svc = MagicMock()
        mock_recovery_svc = MagicMock()
        mock_job_repo = MagicMock()
        mock_job_repo.create_batch.return_value = [
            {"id": "job-1", "platform": "bunjang"},
            {"id": "job-2", "platform": "joongna"},
        ]

        orch = PublishOrchestrator(
            session_repository=mock_repo,
            publish_service=mock_publish_svc,
            recovery_service=mock_recovery_svc,
            job_repo=mock_job_repo,
        )

        session = {
            "selected_platforms_jsonb": ["bunjang", "joongna"],
            "listing_data_jsonb": {"platform_packages": {"bunjang": {}, "joongna": {}}},
            "workflow_meta_jsonb": {},
            "user_id": "user-1",
        }

        result = asyncio.get_event_loop().run_until_complete(
            orch._publish_via_queue("sess-1", session, "awaiting_publish_approval", user_id="user-1")
        )

        mock_job_repo.create_batch.assert_called_once()
        call_kwargs = mock_job_repo.create_batch.call_args[1]
        assert call_kwargs["session_id"] == "sess-1"
        assert call_kwargs["user_id"] == "user-1"
        assert set(call_kwargs["platforms"]) == {"bunjang", "joongna"}


# ── Worker 테스트 ────────────────────────────────────────────────

class TestPublishWorker:
    def test_import(self):
        from app.services.publish_worker import PublishWorker
        assert PublishWorker is not None

    def test_worker_init(self):
        from app.services.publish_worker import PublishWorker
        mock_repo = MagicMock()
        worker = PublishWorker(job_repo=mock_repo, worker_id="test-worker")
        assert worker.worker_id == "test-worker"
        assert worker._running is False
