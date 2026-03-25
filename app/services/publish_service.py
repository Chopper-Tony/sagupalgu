from app.core.config import settings
from app.publishers.joongna_publisher import JoongnaPublisher
from app.publishers.bunjang_publisher import BunjangPublisher
from app.publishers.daangn_publisher import DaangnPublisher

from app.publishers.publisher_interface import (
    PlatformPackage,
    PublishResult,
    PublisherAccountContext,
)


class PublishService:

    PUBLISHER_REGISTRY = {
        "joongna": JoongnaPublisher,
        "bunjang": BunjangPublisher,
        "daangn": DaangnPublisher,
    }

    def get_publisher(self, platform: str):

        publisher_cls = self.PUBLISHER_REGISTRY.get(platform)

        if publisher_cls is None:
            supported = ", ".join(self.PUBLISHER_REGISTRY.keys())
            raise ValueError(
                f"Unsupported platform: {platform}. Supported platforms: {supported}"
            )

        return publisher_cls()

    def build_account_context(self, platform: str) -> PublisherAccountContext:

        if platform == "joongna":

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

        if platform == "bunjang":

            if not settings.bunjang_username or not settings.bunjang_password:
                raise ValueError("Bunjang credentials are not configured")

            return PublisherAccountContext(
                platform_account_id="env-bunjang",
                platform="bunjang",
                auth_type="username_password",
                secret_payload={
                    "username": settings.bunjang_username,
                    "password": settings.bunjang_password,
                },
            )

        if platform == "daangn":
            raise ValueError("Daangn publisher not implemented yet")

        raise ValueError(f"Unsupported platform: {platform}")

    def build_platform_packages(
        self,
        canonical_listing: dict,
        platform_targets: list[str],
    ) -> dict:
        """플랫폼별 가격 차등 패키지 생성. prepare_publish 단계에서 호출."""
        base_price = int(canonical_listing.get("price", 0))
        packages: dict = {}
        for platform in platform_targets:
            if platform == "bunjang":
                price = base_price + 10000
            elif platform == "daangn":
                price = max(base_price - 4000, 0)
            else:
                price = base_price
            packages[platform] = {
                "title": canonical_listing.get("title", ""),
                "body": canonical_listing.get("description", ""),
                "price": price,
                "images": canonical_listing.get("images", []),
            }
        return packages

    async def execute_publish(
        self,
        platforms: list[str],
        packages: dict,
    ) -> tuple[dict, bool]:
        """
        플랫폼 목록을 순회하며 게시 실행.
        각 플랫폼에 타임아웃을 적용하고, 에러를 정규화 분류한다.

        Returns:
            (publish_results, any_failure)
        """
        import asyncio
        import logging

        from app.domain.publish_policy import (
            PUBLISH_TIMEOUT_SECONDS,
            classify_error,
        )

        logger = logging.getLogger(__name__)
        publish_results: dict = {}
        any_failure = False

        for platform in platforms:
            payload = packages.get(platform)
            if not payload:
                classification = classify_error("missing_platform_package")
                publish_results[platform] = {
                    "success": False,
                    "platform": platform,
                    "error_code": classification["error_code"],
                    "error_message": f"{platform} 패키지 없음",
                    "auto_recoverable": classification["auto_recoverable"],
                }
                any_failure = True
                continue

            try:
                result = await asyncio.wait_for(
                    self.publish(platform=platform, payload=payload),
                    timeout=PUBLISH_TIMEOUT_SECONDS,
                )
                error_code = result.error_code or ""
                error_message = result.error_message or ""
                classification = classify_error(error_code, error_message)

                publish_results[platform] = {
                    "success": result.success,
                    "platform": result.platform,
                    "external_listing_id": result.external_listing_id,
                    "external_url": result.external_url,
                    "error_code": classification["error_code"] if not result.success else None,
                    "error_message": error_message if not result.success else None,
                    "evidence_path": result.evidence_path,
                    "auto_recoverable": classification["auto_recoverable"] if not result.success else None,
                }
                if not result.success:
                    any_failure = True
                    logger.warning(
                        "publish_failed platform=%s error_code=%s category=%s",
                        platform, classification["error_code"], classification["category"],
                    )
                else:
                    logger.info("publish_success platform=%s url=%s", platform, result.external_url)

            except asyncio.TimeoutError:
                classification = classify_error("timeout")
                publish_results[platform] = {
                    "success": False,
                    "platform": platform,
                    "error_code": "timeout",
                    "error_message": f"{platform} 게시 {PUBLISH_TIMEOUT_SECONDS}초 타임아웃 초과",
                    "auto_recoverable": True,
                }
                any_failure = True
                logger.warning("publish_timeout platform=%s timeout=%ds", platform, PUBLISH_TIMEOUT_SECONDS)

            except Exception as e:
                classification = classify_error("publish_exception", str(e))
                publish_results[platform] = {
                    "success": False,
                    "platform": platform,
                    "error_code": classification["error_code"],
                    "error_message": str(e),
                    "auto_recoverable": classification["auto_recoverable"],
                }
                any_failure = True
                logger.error("publish_exception platform=%s error=%s", platform, e)

        return publish_results, any_failure

    async def publish(self, platform: str, payload: dict) -> PublishResult:

        publisher = self.get_publisher(platform)

        account = self.build_account_context(platform)

        package = PlatformPackage(
            platform=platform,
            payload=payload,
        )

        result = await publisher.publish(
            package=package,
            account=account,
        )

        return result