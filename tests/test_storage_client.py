"""
Supabase Storage 클라이언트 unit 테스트

supabase 클라이언트를 mock으로 대체해 HTTP 호출 없이 검증.
"""
from unittest.mock import MagicMock, patch

import pytest

from app.storage.storage_client import get_public_url, upload_image


def _make_mock_client(public_url: str = "https://example.supabase.co/storage/v1/object/public/product-images/uploads/test.jpg"):
    mock_storage = MagicMock()
    mock_storage.from_.return_value.upload.return_value = None
    mock_storage.from_.return_value.get_public_url.return_value = public_url

    mock_client = MagicMock()
    mock_client.storage = mock_storage
    return mock_client


class TestUploadImage:

    @pytest.mark.unit
    def test_returns_public_url(self):
        expected_url = "https://proj.supabase.co/storage/v1/object/public/product-images/uploads/test.jpg"
        mock_client = _make_mock_client(expected_url)

        with patch("app.storage.storage_client._get_supabase_client", return_value=mock_client):
            url = upload_image(b"fake-image-bytes", "test.jpg")

        assert url == expected_url

    @pytest.mark.unit
    def test_upload_called_with_correct_path(self):
        mock_client = _make_mock_client()

        with patch("app.storage.storage_client._get_supabase_client", return_value=mock_client), \
             patch("app.storage.storage_client.settings") as mock_settings:
            mock_settings.storage_bucket_name = "product-images"
            upload_image(b"bytes", "photo.jpg", content_type="image/jpeg")

        mock_client.storage.from_.assert_called_with("product-images")
        call_kwargs = mock_client.storage.from_.return_value.upload.call_args
        assert call_kwargs.kwargs["path"] == "uploads/photo.jpg"

    @pytest.mark.unit
    def test_auto_generates_filename_when_none(self):
        mock_client = _make_mock_client()

        with patch("app.storage.storage_client._get_supabase_client", return_value=mock_client):
            upload_image(b"bytes", filename=None, content_type="image/jpeg")

        call_kwargs = mock_client.storage.from_.return_value.upload.call_args
        path = call_kwargs.kwargs["path"]
        assert path.startswith("uploads/")
        assert path.endswith(".jpg")

    @pytest.mark.unit
    def test_content_type_passed_to_storage(self):
        mock_client = _make_mock_client()

        with patch("app.storage.storage_client._get_supabase_client", return_value=mock_client):
            upload_image(b"bytes", "img.png", content_type="image/png")

        call_kwargs = mock_client.storage.from_.return_value.upload.call_args
        assert call_kwargs.kwargs["file_options"]["content-type"] == "image/png"

    @pytest.mark.unit
    def test_upsert_option_enabled(self):
        mock_client = _make_mock_client()

        with patch("app.storage.storage_client._get_supabase_client", return_value=mock_client):
            upload_image(b"bytes", "img.jpg")

        call_kwargs = mock_client.storage.from_.return_value.upload.call_args
        assert call_kwargs.kwargs["file_options"]["upsert"] == "true"


class TestGetPublicUrl:

    @pytest.mark.unit
    def test_returns_url_from_storage(self):
        mock_client = _make_mock_client("https://example.co/public/path/to/file.jpg")

        with patch("app.storage.storage_client._get_supabase_client", return_value=mock_client):
            url = get_public_url("path/to/file.jpg")

        assert url == "https://example.co/public/path/to/file.jpg"

    @pytest.mark.unit
    def test_delegates_to_correct_bucket(self):
        mock_client = _make_mock_client()

        with patch("app.storage.storage_client._get_supabase_client", return_value=mock_client), \
             patch("app.storage.storage_client.settings") as mock_settings:
            mock_settings.storage_bucket_name = "my-bucket"
            get_public_url("some/path.jpg")

        mock_client.storage.from_.assert_called_with("my-bucket")
