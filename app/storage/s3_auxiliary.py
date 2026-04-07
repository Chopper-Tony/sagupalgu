"""
app/storage/s3_auxiliary.py -- S3 보조 스토리지 (게시 증적 스크린샷).

Supabase Storage 대체가 아니라, 게시 증적 스크린샷을 S3에 아카이빙하는 용도.
S3_AUXILIARY_ENABLED=false(기본값)이면 모든 함수는 즉시 None을 반환한다.

사용법:
    from app.storage.s3_auxiliary import archive_screenshot
    url = await archive_screenshot("/path/to/screenshot.png", "session-123")
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path

from app.core.config import settings

logger = logging.getLogger(__name__)


async def archive_screenshot(
    file_path: str,
    session_id: str,
) -> str | None:
    """게시 증적 스크린샷을 S3에 비동기 업로드한다.

    fire-and-forget 패턴: 실패해도 예외를 발생시키지 않는다.

    Returns:
        S3 URL 문자열 또는 None (비활성/실패 시).
    """
    if not settings.s3_auxiliary_enabled:
        return None

    path = Path(file_path)
    if not path.exists():
        logger.warning("archive_screenshot: 파일 없음 %s", file_path)
        return None

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    s3_key = f"screenshots/{session_id}/{timestamp}_{path.name}"

    try:
        file_bytes = path.read_bytes()
        url = await asyncio.to_thread(_upload_to_s3, file_bytes, s3_key)
        logger.info("screenshot archived", extra={"s3_key": s3_key, "session_id": session_id})
        return url
    except Exception:
        logger.warning("S3 archive failed (non-fatal)", exc_info=True)
        return None


def _upload_to_s3(file_bytes: bytes, s3_key: str) -> str:
    """boto3 동기 업로드. asyncio.to_thread에서 호출된다."""
    import boto3  # lazy import

    client = boto3.client(
        "s3",
        region_name=settings.s3_auxiliary_region,
    )
    bucket = settings.s3_auxiliary_bucket

    client.put_object(
        Bucket=bucket,
        Key=s3_key,
        Body=file_bytes,
        ContentType="image/png",
    )

    return f"https://{bucket}.s3.{settings.s3_auxiliary_region}.amazonaws.com/{s3_key}"
