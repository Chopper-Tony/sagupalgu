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