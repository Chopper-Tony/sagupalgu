"""
당근마켓 게시 어댑터 — Android 에뮬레이터 기반 (uiautomator2).

필수 환경:
  - Android 에뮬레이터 또는 실기기 (ADB 연결)
  - uiautomator2 설치: pip install uiautomator2 && python -m uiautomator2 init
  - DAANGN_DEVICE_ID 환경변수 설정 (adb devices로 확인)
  - 당근마켓 앱 로그인 완료 (수동 — SMS 인증 필요)
"""
import asyncio
import logging

from app.publishers._legacy_compat import LegacyDaangnPublisher
from app.publishers._legacy_utils import to_legacy_listing_package
from app.publishers.publisher_interface import (
    PlatformPackage,
    PlatformPublisher,
    PublishResult,
    PublisherAccountContext,
)

logger = logging.getLogger(__name__)


class DaangnPublisher(PlatformPublisher):
    async def publish(
        self, package: PlatformPackage, account: PublisherAccountContext,
    ) -> PublishResult:
        if LegacyDaangnPublisher is None:
            logger.error("uiautomator2 미설치 — pip install uiautomator2 필요")
            return PublishResult(
                success=False,
                platform="daangn",
                error_code="dependency_missing",
                error_message="uiautomator2가 설치되지 않았습니다",
            )

        device_id = account.secret_payload.get("device_id")
        if not device_id:
            logger.error("DAANGN_DEVICE_ID 미설정")
            return PublishResult(
                success=False,
                platform="daangn",
                error_code="credential_missing",
                error_message="DAANGN_DEVICE_ID가 설정되지 않았습니다",
            )

        legacy_pkg = to_legacy_listing_package(package.payload)
        logger.info("daangn_publish_start device=%s title=%s", device_id, package.payload.get("title", ""))

        try:
            publisher = LegacyDaangnPublisher(device_serial=device_id)
            result = await asyncio.to_thread(publisher.publish, legacy_pkg)

            if result.success:
                logger.info("daangn_publish_success listing_id=%s", result.listing_id)
            else:
                logger.warning("daangn_publish_failed error=%s", result.error_message)

            return PublishResult(
                success=result.success,
                platform="daangn",
                external_listing_id=getattr(result, "listing_id", None),
                external_url=getattr(result, "listing_url", None),
                error_code=getattr(result, "error_code", None) if not result.success else None,
                error_message=getattr(result, "error_message", None) if not result.success else None,
                evidence_path=str(result.screenshot_path) if getattr(result, "screenshot_path", None) else None,
            )
        except Exception as e:
            logger.error("daangn_publish_exception error=%s", e)
            return PublishResult(
                success=False,
                platform="daangn",
                error_code="publish_exception",
                error_message=str(e),
            )
