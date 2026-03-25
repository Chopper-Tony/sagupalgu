from app.publishers._legacy_compat import LegacyJoongnaPublisher

from app.core.config import settings
from app.publishers.publisher_interface import (
    PlatformPackage,
    PublisherAccountContext,
    PublishResult,
    PlatformPublisher,
)
from app.publishers._legacy_utils import to_legacy_listing_package


class JoongnaPublisher(PlatformPublisher):
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

        return PublishResult(
            success=result.success,
            platform="joongna",
            external_listing_id=result.listing_id,
            external_url=result.listing_url,
            error_message=result.error_message,
            evidence_path=str(result.screenshot_path)
            if result.screenshot_path
            else None,
        )