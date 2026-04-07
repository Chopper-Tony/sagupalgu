import logging
import re

from app.publishers._legacy_compat import LegacyJoongnaPublisher

from app.core.config import settings
from app.publishers.publisher_interface import (
    PlatformPackage,
    PublisherAccountContext,
    PublishResult,
    PlatformPublisher,
)
from app.publishers._legacy_utils import to_legacy_listing_package

logger = logging.getLogger(__name__)


def _extract_joongna_product_id(url: str | None) -> str | None:
    """URL에서 중고나라 상품 ID를 추출한다."""
    if not url:
        return None
    # /product/227216506 형태
    m = re.search(r"/product/(\d+)", url)
    if m:
        return m.group(1)
    # form?type=complete&completeSeq=227216506 형태
    m = re.search(r"completeSeq=(\d+)", url)
    if m:
        return m.group(1)
    # URL 끝에 /숫자 형태
    m = re.search(r"/(\d+)(?:\?|$)", url)
    if m:
        return m.group(1)
    return None


class JoongnaPublisher(PlatformPublisher):
    @classmethod
    def build_account_context(cls, settings) -> PublisherAccountContext:
        if not settings.joongna_username or not settings.joongna_password:
            raise ValueError("Joongna credentials are not configured")
        return PublisherAccountContext(
            platform_account_id="env-joongna",
            platform="joongna",
            auth_type="id_password",
            secret_payload={
                "username": settings.joongna_username,
                "password": settings.joongna_password,
            },
        )

    async def publish(
        self,
        package: PlatformPackage,
        account: PublisherAccountContext,
    ) -> PublishResult:
        legacy_pkg = to_legacy_listing_package(package.payload)

        publisher = LegacyJoongnaPublisher(
            headless=settings.publish_headless,
            slow_mo=settings.publish_slow_mo,
        )

        result = await publisher.run(
            package=legacy_pkg,
            phone=account.secret_payload.get("username", ""),
            password=account.secret_payload.get("password", ""),
        )

        # legacy 결과에서 상품 ID 추출 후 정규 URL 보정
        product_id = result.listing_id or _extract_joongna_product_id(result.listing_url)
        canonical_url = f"https://web.joongna.com/product/{product_id}" if product_id else result.listing_url
        if result.success and not product_id:
            logger.warning("[중고나라] 게시 성공했으나 상품 ID 추출 실패. listing_url=%s", result.listing_url)

        return PublishResult(
            success=result.success,
            platform="joongna",
            external_listing_id=product_id,
            external_url=canonical_url,
            error_message=result.error_message,
            evidence_path=str(result.screenshot_path)
            if result.screenshot_path
            else None,
        )