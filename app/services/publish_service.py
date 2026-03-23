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