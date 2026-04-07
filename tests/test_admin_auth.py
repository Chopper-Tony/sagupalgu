"""Admin API 인증 + Worker 안정성 테스트."""
import asyncio

import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi.testclient import TestClient


@pytest.fixture
def app_with_admin_key():
    """ADMIN_API_KEY가 설정된 앱."""
    with patch("app.core.config.get_settings") as mock_settings:
        s = MagicMock()
        s.environment = "local"
        s.debug = True
        s.api_v1_prefix = "/api/v1"
        s.allowed_origins = "http://localhost:3000"
        s.admin_api_key = "test-admin-secret"
        s.run_publish_worker = False
        s.supabase_jwt_secret = None
        mock_settings.return_value = s

        from app.main import create_app
        app = create_app()
        yield TestClient(app)


@pytest.fixture
def app_without_admin_key():
    """ADMIN_API_KEY가 미설정된 앱."""
    with patch("app.core.config.get_settings") as mock_settings:
        s = MagicMock()
        s.environment = "local"
        s.debug = True
        s.api_v1_prefix = "/api/v1"
        s.allowed_origins = "http://localhost:3000"
        s.admin_api_key = None
        s.run_publish_worker = False
        s.supabase_jwt_secret = None
        mock_settings.return_value = s

        from app.main import create_app
        app = create_app()
        yield TestClient(app)


class TestAdminAuth:
    """Admin API 인증 검증."""

    def test_admin_api_requires_key(self, app_with_admin_key):
        """X-Admin-Key 없이 호출하면 403."""
        r = app_with_admin_key.get("/api/v1/admin/publish-queue/stats")
        assert r.status_code == 403

    def test_admin_api_wrong_key_403(self, app_with_admin_key):
        """잘못된 키로 호출하면 403."""
        r = app_with_admin_key.get(
            "/api/v1/admin/publish-queue/stats",
            headers={"x-admin-key": "wrong-key"},
        )
        assert r.status_code == 403

    @patch("app.api.admin_router._get_job_repo")
    def test_admin_api_correct_key_passes(self, mock_repo, app_with_admin_key):
        """올바른 키면 통과."""
        mock_repo.return_value.get_queue_stats.return_value = {"pending": 0}
        r = app_with_admin_key.get(
            "/api/v1/admin/publish-queue/stats",
            headers={"x-admin-key": "test-admin-secret"},
        )
        assert r.status_code == 200

    def test_admin_api_disabled_when_no_key_configured(self, app_without_admin_key):
        """ADMIN_API_KEY 미설정 시 모든 요청 403."""
        r = app_without_admin_key.get("/api/v1/admin/publish-queue/stats")
        assert r.status_code == 403

    def test_admin_api_disabled_even_with_header(self, app_without_admin_key):
        """ADMIN_API_KEY 미설정이면 헤더를 보내도 403."""
        r = app_without_admin_key.get(
            "/api/v1/admin/publish-queue/stats",
            headers={"x-admin-key": "any-key"},
        )
        assert r.status_code == 403


class TestWorkerTaskTracking:
    """PublishWorker task 추적 검증."""

    def test_worker_init_has_active_tasks_set(self):
        """워커 초기화 시 _active_tasks set이 존재한다."""
        from app.services.publish_worker import PublishWorker
        mock_repo = MagicMock()
        worker = PublishWorker(job_repo=mock_repo)
        assert isinstance(worker._active_tasks, set)
        assert len(worker._active_tasks) == 0

    def test_worker_init_active_jobs_zero(self):
        """워커 초기화 시 _active_jobs가 0이다."""
        from app.services.publish_worker import PublishWorker
        mock_repo = MagicMock()
        worker = PublishWorker(job_repo=mock_repo)
        assert worker._active_jobs == 0

    @pytest.mark.asyncio
    async def test_worker_stop_is_graceful(self):
        """stop()이 running flag를 False로 설정한다."""
        from app.services.publish_worker import PublishWorker
        mock_repo = MagicMock()
        worker = PublishWorker(job_repo=mock_repo)
        worker._running = True
        await worker.stop()
        assert worker._running is False

    @pytest.mark.asyncio
    async def test_worker_crash_isolation(self):
        """_process_job 내부 예외가 워커 전체를 죽이지 않는다."""
        from app.services.publish_worker import PublishWorker
        mock_repo = MagicMock()
        mock_repo.claim.side_effect = RuntimeError("DB 연결 실패")
        worker = PublishWorker(job_repo=mock_repo)

        # 예외가 발생해도 _process_job은 조용히 로깅하고 종료
        job = {"id": "j1", "session_id": "s1", "platform": "bunjang", "user_id": "u1"}
        await worker._process_job(job)  # 예외 안 터짐


class TestQueuePathE2E:
    """Queue 모드 happy path + failure/retry 시나리오."""

    @pytest.mark.asyncio
    async def test_queue_happy_path(self):
        """enqueue → claim → execute → complete → session update."""
        from app.services.publish_worker import PublishWorker
        from app.publishers.publisher_interface import PublishResult

        mock_repo = MagicMock()
        mock_repo.claim.return_value = True
        worker = PublishWorker(job_repo=mock_repo)

        mock_result = PublishResult(
            success=True,
            platform="bunjang",
            external_listing_id="ext-123",
            external_url="https://m.bunjang.co.kr/products/ext-123",
        )

        job = {
            "id": "j-happy",
            "session_id": "s-happy",
            "platform": "bunjang",
            "user_id": "u1",
            "attempt_count": 0,
        }

        with patch.object(worker, "_execute_publish", new_callable=AsyncMock) as mock_exec, \
             patch.object(worker, "_update_session_on_complete", new_callable=AsyncMock) as mock_update:
            mock_exec.return_value = {
                "success": True,
                "external_listing_id": "ext-123",
                "external_url": "https://m.bunjang.co.kr/products/ext-123",
                "evidence_urls": [],
                "error_code": "",
                "error_message": "",
            }
            await worker._process_job(job)

        mock_repo.claim.assert_called_once_with("j-happy", worker.worker_id)
        mock_repo.start.assert_called_once()
        mock_repo.complete.assert_called_once()
        mock_update.assert_called_once()

    @pytest.mark.asyncio
    async def test_queue_failure_retry_path(self):
        """실패 → fail 기록 → _update_session_on_failure 호출."""
        from app.services.publish_worker import PublishWorker

        mock_repo = MagicMock()
        mock_repo.claim.return_value = True
        worker = PublishWorker(job_repo=mock_repo)

        job = {
            "id": "j-fail",
            "session_id": "s-fail",
            "platform": "joongna",
            "user_id": "u1",
            "attempt_count": 0,
        }

        with patch.object(worker, "_execute_publish", new_callable=AsyncMock) as mock_exec, \
             patch.object(worker, "_update_session_on_failure", new_callable=AsyncMock) as mock_fail_update:
            mock_exec.return_value = {
                "success": False,
                "error_code": "timeout",
                "error_message": "게시 180초 타임아웃 초과",
                "evidence_urls": [],
                "external_listing_id": None,
                "external_url": None,
            }
            await worker._process_job(job)

        mock_repo.fail.assert_called_once()
        fail_kwargs = mock_repo.fail.call_args
        assert fail_kwargs[1]["error_code"] == "timeout"
        assert fail_kwargs[1]["auto_recoverable"] is True
        mock_fail_update.assert_called_once()
