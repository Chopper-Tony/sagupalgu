"""Admin API 인증 테스트."""
import pytest
from unittest.mock import patch, MagicMock
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

    def test_worker_init_has_tasks_set(self):
        """워커 초기화 시 _tasks set이 존재한다."""
        from app.services.publish_worker import PublishWorker
        mock_repo = MagicMock()
        worker = PublishWorker(job_repo=mock_repo)
        assert isinstance(worker._tasks, set)
        assert len(worker._tasks) == 0

    def test_worker_active_task_count_property(self):
        """active_task_count 프로퍼티가 정상 동작한다."""
        from app.services.publish_worker import PublishWorker
        mock_repo = MagicMock()
        worker = PublishWorker(job_repo=mock_repo)
        assert worker.active_task_count == 0

    @pytest.mark.asyncio
    async def test_worker_stop_is_graceful(self):
        """stop()이 running flag를 False로 설정한다."""
        from app.services.publish_worker import PublishWorker
        mock_repo = MagicMock()
        worker = PublishWorker(job_repo=mock_repo)
        worker._running = True
        await worker.stop()
        assert worker._running is False
