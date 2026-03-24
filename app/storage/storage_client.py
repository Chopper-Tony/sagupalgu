"""
app/storage/storage_client.py — Supabase Storage 클라이언트.

이미지 업로드 및 공개 URL 조회를 담당한다.

활성화 방법:
  Supabase 대시보드 → Storage → Buckets에서
  버킷명(기본값: "product-images")을 Public으로 생성한 뒤
  .env에 STORAGE_BUCKET_NAME=<버킷명> 설정.

사용법:
  url = await upload_image(file_bytes, "iphone_front.jpg")
  # → https://<project>.supabase.co/storage/v1/object/public/product-images/uploads/iphone_front.jpg
"""
from __future__ import annotations

import logging
import uuid
from functools import lru_cache

from app.core.config import settings

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _get_supabase_client():
    """Supabase 클라이언트 싱글턴. 최초 호출 시 생성."""
    from supabase import create_client  # lazy import — 미설치 환경에서도 모듈 import 가능
    return create_client(settings.supabase_url, settings.supabase_service_role_key)


def upload_image(
    file_bytes: bytes,
    filename: str | None = None,
    content_type: str = "image/jpeg",
) -> str:
    """이미지를 Supabase Storage에 업로드하고 공개 URL을 반환한다.

    Args:
        file_bytes: 업로드할 이미지 바이트.
        filename: 저장 파일명. None이면 UUID 자동 생성.
        content_type: MIME 타입 (기본값: image/jpeg).

    Returns:
        업로드된 이미지의 공개 URL 문자열.

    Raises:
        Exception: Supabase Storage 업로드 실패 시.
    """
    if filename is None:
        ext = "jpg" if "jpeg" in content_type else content_type.split("/")[-1]
        filename = f"{uuid.uuid4()}.{ext}"

    bucket = settings.storage_bucket_name
    path = f"uploads/{filename}"

    client = _get_supabase_client()
    client.storage.from_(bucket).upload(
        path=path,
        file=file_bytes,
        file_options={"content-type": content_type, "upsert": "true"},
    )

    public_url = client.storage.from_(bucket).get_public_url(path)
    logger.info("image uploaded", extra={"path": path, "bucket": bucket})
    return public_url


def get_public_url(path: str) -> str:
    """Storage 경로로부터 공개 URL을 반환한다."""
    client = _get_supabase_client()
    return client.storage.from_(settings.storage_bucket_name).get_public_url(path)
