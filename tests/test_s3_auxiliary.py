"""S3 보조 스토리지 유닛 테스트."""
import asyncio
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# boto3가 설치되지 않은 환경에서도 테스트 수집 가능하도록 mock 주입
if "boto3" not in sys.modules:
    sys.modules["boto3"] = MagicMock()


@pytest.fixture
def _enable_s3(monkeypatch):
    """S3 보조 스토리지를 활성화한다."""
    monkeypatch.setattr("app.core.config.get_settings", lambda: MagicMock(
        s3_auxiliary_enabled=True,
        s3_auxiliary_bucket="test-bucket",
        s3_auxiliary_region="ap-northeast-2",
    ))


@pytest.fixture
def _disable_s3(monkeypatch):
    """S3 보조 스토리지를 비활성화한다."""
    monkeypatch.setattr("app.core.config.get_settings", lambda: MagicMock(
        s3_auxiliary_enabled=False,
    ))


class TestArchiveScreenshot:
    """archive_screenshot 함수 테스트."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_disabled_returns_none(self, _disable_s3):
        from app.storage.s3_auxiliary import archive_screenshot
        result = await archive_screenshot("/any/path.png", "session-1")
        assert result is None

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_missing_file_returns_none(self, _enable_s3):
        from app.storage.s3_auxiliary import archive_screenshot
        result = await archive_screenshot("/nonexistent/file.png", "session-1")
        assert result is None

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_successful_upload(self, _enable_s3, tmp_path):
        screenshot = tmp_path / "test.png"
        screenshot.write_bytes(b"fake-png-data")

        mock_client = MagicMock()
        with patch("app.storage.s3_auxiliary._upload_to_s3") as mock_upload:
            mock_upload.return_value = "https://test-bucket.s3.ap-northeast-2.amazonaws.com/screenshots/s1/test.png"
            from app.storage.s3_auxiliary import archive_screenshot
            result = await archive_screenshot(str(screenshot), "s1")

        assert result is not None
        assert "s3" in result
        assert "s1" in mock_upload.call_args[0][1]

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_upload_failure_returns_none(self, _enable_s3, tmp_path):
        screenshot = tmp_path / "test.png"
        screenshot.write_bytes(b"fake-png-data")

        with patch("app.storage.s3_auxiliary._upload_to_s3", side_effect=Exception("S3 down")):
            from app.storage.s3_auxiliary import archive_screenshot
            result = await archive_screenshot(str(screenshot), "s1")

        assert result is None


class TestUploadToS3:
    """_upload_to_s3 내부 함수 테스트."""

    @pytest.mark.unit
    def test_calls_boto3_put_object(self, _enable_s3):
        mock_client = MagicMock()
        with patch("boto3.client", return_value=mock_client):
            from app.storage.s3_auxiliary import _upload_to_s3
            url = _upload_to_s3(b"data", "screenshots/s1/test.png")

        mock_client.put_object.assert_called_once()
        call_kwargs = mock_client.put_object.call_args[1]
        assert call_kwargs["Key"] == "screenshots/s1/test.png"
        assert call_kwargs["ContentType"] == "image/png"
        assert "s3" in url

    @pytest.mark.unit
    def test_returns_correct_url_format(self, _enable_s3):
        mock_client = MagicMock()
        with patch("boto3.client", return_value=mock_client):
            from app.storage.s3_auxiliary import _upload_to_s3
            url = _upload_to_s3(b"data", "screenshots/s1/shot.png")

        assert url == "https://test-bucket.s3.ap-northeast-2.amazonaws.com/screenshots/s1/shot.png"
