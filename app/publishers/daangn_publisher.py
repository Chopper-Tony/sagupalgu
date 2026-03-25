import asyncio
from app.publishers._legacy_compat import LegacyDaangnPublisher
from app.publishers.publisher_interface import PlatformPackage, PublisherAccountContext, PublishResult, PlatformPublisher
from app.publishers._legacy_utils import to_legacy_listing_package

class DaangnPublisher(PlatformPublisher):
    async def publish(self, package: PlatformPackage, account: PublisherAccountContext) -> PublishResult:
        legacy_pkg = to_legacy_listing_package(package.payload)
        publisher = LegacyDaangnPublisher(
            device_serial=account.secret_payload.get("device_id"),
        )
        result = await asyncio.to_thread(publisher.publish, legacy_pkg)
        return PublishResult(
            success=result.success,
            platform="daangn",
            external_listing_id=result.listing_id,
            external_url=result.listing_url,
            error_message=result.error_message,
            evidence_path=str(result.screenshot_path) if result.screenshot_path else None,
        )
