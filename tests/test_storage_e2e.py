"""
Supabase Storage E2E 테스트

USE_CLOUD_STORAGE 플래그에 따른 업로드 경로 분기 검증.
storage_client는 mock으로 대체 (실제 Supabase 불필요).
"""
import io
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


def _create_test_app(use_cloud: bool = False):
    """테스트용 FastAPI 앱 생성 (설정 오버라이드)."""
    from app.main import create_app

    app = create_app()

    # SessionService mock (AsyncMock으로 call_args 추적 가능)
    mock_svc = MagicMock()
    mock_svc.attach_images = AsyncMock(return_value={
        "session_id": "test-session",
        "status": "images_uploaded",
        "image_urls": [],
    })

    from app.dependencies import get_session_service
    app.dependency_overrides[get_session_service] = lambda: mock_svc

    # 인증 우회
    from app.core.auth import get_current_user, AuthenticatedUser
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(user_id="test-user")

    # use_cloud_storage 설정 오버라이드
    from app.core.config import get_settings

    mock_settings = MagicMock()
    real = get_settings()
    mock_settings.use_cloud_storage = use_cloud
    # upload_images에서 사용하는 다른 속성은 불필요 (get_settings만 패치)

    from app.core import config as config_module
    _original_get_settings = config_module.get_settings

    def _mock_get_settings():
        return mock_settings

    config_module.get_settings = _mock_get_settings

    client = TestClient(app)
    return client, mock_svc, config_module, _original_get_settings


def _make_fake_file(filename="test.jpg", content=b"fake-jpeg-data", content_type="image/jpeg"):
    """테스트용 업로드 파일 생성."""
    return ("files", (filename, io.BytesIO(content), content_type))


class TestCloudStorageFlagOff:
    """USE_CLOUD_STORAGE=False 시 로컬 경로 사용 검증."""

    @pytest.mark.unit
    def test_cloud_storage_flag_off_uses_local(self):
        """플래그 off이면 /uploads/ 로컬 경로를 사용한다."""
        client, mock_svc, config_module, original = _create_test_app(use_cloud=False)
        try:
            response = client.post(
                "/api/v1/sessions/test-session/images",
                files=[_make_fake_file()],
            )
            assert response.status_code == 200

            # attach_images에 전달된 image_urls 확인
            call_kwargs = mock_svc.attach_images.call_args
            urls = call_kwargs.kwargs.get("image_urls") or call_kwargs[1].get("image_urls", [])
            assert len(urls) == 1
            assert urls[0].startswith("/uploads/test-session/")
            assert not urls[0].startswith("http")
        finally:
            config_module.get_settings = original


class TestCloudStorageFlagOn:
    """USE_CLOUD_STORAGE=True 시 storage_client 호출 검증."""

    @pytest.mark.unit
    def test_cloud_storage_flag_on_calls_upload(self):
        """플래그 on이면 storage_client.upload_image을 호출하고 public URL을 사용한다."""
        cloud_url = "https://proj.supabase.co/storage/v1/object/public/product-images/uploads/test-session/img.jpg"
        client, mock_svc, config_module, original = _create_test_app(use_cloud=True)
        try:
            with patch(
                "app.storage.storage_client.upload_image",
                return_value=cloud_url,
            ) as mock_upload:
                response = client.post(
                    "/api/v1/sessions/test-session/images",
                    files=[_make_fake_file()],
                )
                assert response.status_code == 200

                # storage_client.upload_image 호출 확인
                mock_upload.assert_called_once()
                call_args = mock_upload.call_args
                # 첫 번째 인자: file bytes
                assert call_args[0][0] == b"fake-jpeg-data"
                # 두 번째 인자: session_id/filename 형식
                assert call_args[0][1].startswith("test-session/")

                # attach_images에 전달된 URL이 cloud URL인지 확인
                attach_kwargs = mock_svc.attach_images.call_args
                urls = attach_kwargs.kwargs.get("image_urls") or attach_kwargs[1].get("image_urls", [])
                assert len(urls) == 1
                assert urls[0] == cloud_url
        finally:
            config_module.get_settings = original


class TestPublicUrlFormat:
    """Public URL 형식 검증."""

    @pytest.mark.unit
    def test_public_url_format(self):
        """Supabase Storage public URL은 https로 시작하고 /storage/v1/object/public/ 경로를 포함한다."""
        cloud_url = "https://myproj.supabase.co/storage/v1/object/public/product-images/uploads/sess123/photo.jpg"
        client, mock_svc, config_module, original = _create_test_app(use_cloud=True)
        try:
            with patch(
                "app.storage.storage_client.upload_image",
                return_value=cloud_url,
            ):
                response = client.post(
                    "/api/v1/sessions/test-session/images",
                    files=[_make_fake_file()],
                )
                assert response.status_code == 200

                attach_kwargs = mock_svc.attach_images.call_args
                urls = attach_kwargs.kwargs.get("image_urls") or attach_kwargs[1].get("image_urls", [])
                url = urls[0]
                assert url.startswith("https://")
                assert "/storage/v1/object/public/" in url
        finally:
            config_module.get_settings = original


class TestFallbackToLocal:
    """Storage 실패 시 로컬 fallback 검증."""

    @pytest.mark.unit
    def test_fallback_to_local_on_upload_error(self):
        """클라우드 업로드 실패 시 로컬 경로로 fallback한다."""
        client, mock_svc, config_module, original = _create_test_app(use_cloud=True)
        try:
            with patch(
                "app.storage.storage_client.upload_image",
                side_effect=Exception("Supabase Storage 연결 실패"),
            ):
                response = client.post(
                    "/api/v1/sessions/test-session/images",
                    files=[_make_fake_file()],
                )
                # 실패해도 200 — 로컬 fallback 성공
                assert response.status_code == 200

                attach_kwargs = mock_svc.attach_images.call_args
                urls = attach_kwargs.kwargs.get("image_urls") or attach_kwargs[1].get("image_urls", [])
                assert len(urls) == 1
                # fallback: 로컬 경로
                assert urls[0].startswith("/uploads/test-session/")
                assert not urls[0].startswith("http")
        finally:
            config_module.get_settings = original
