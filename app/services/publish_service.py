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
            return PublisherAccountContext(
                platform_account_id="env-daangn",
                platform="daangn",
                auth_type="device",
                secret_payload={
                    "device_id": settings.daangn_device_id or "",
                },
            )

        raise ValueError(f"Unsupported platform: {platform}")

    @staticmethod
    def _resolve_image_paths(images: list) -> list[str]:
        """URL 경로(/uploads/...)를 파일 시스템 절대 경로로 변환."""
        import os
        resolved = []
        for img in images:
            if isinstance(img, str) and img.startswith("/uploads/"):
                # /uploads/session_id/file.jpg → ./uploads/session_id/file.jpg
                fs_path = os.path.abspath(img.lstrip("/"))
                if os.path.exists(fs_path):
                    resolved.append(fs_path)
                else:
                    resolved.append(img)  # 존재하지 않으면 원본 유지
            else:
                resolved.append(str(img))
        return resolved

    def build_platform_packages(
        self,
        canonical_listing: dict,
        platform_targets: list[str],
    ) -> dict:
        """플랫폼별 가격 차등 패키지 생성. prepare_publish 단계에서 호출."""
        base_price = int(canonical_listing.get("price", 0))
        images = self._resolve_image_paths(canonical_listing.get("images", []))
        category = ""
        product = canonical_listing.get("product") or {}
        if isinstance(product, dict):
            category = product.get("category", "")

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
                "images": images,
                "category": category,
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

        async def _publish_one(platform: str) -> dict:
            """단일 플랫폼 게시 실행 (타임아웃·에러 분류 포함)."""
            payload = packages.get(platform)
            if not payload:
                classification = classify_error("missing_platform_package")
                return {
                    "success": False, "platform": platform,
                    "error_code": classification["error_code"],
                    "error_message": f"{platform} 패키지 없음",
                    "auto_recoverable": classification["auto_recoverable"],
                }
            try:
                result = await asyncio.wait_for(
                    self.publish(platform=platform, payload=payload),
                    timeout=PUBLISH_TIMEOUT_SECONDS,
                )
                error_code = result.error_code or ""
                error_message = result.error_message or ""
                classification = classify_error(error_code, error_message)

                entry = {
                    "success": result.success, "platform": result.platform,
                    "external_listing_id": result.external_listing_id,
                    "external_url": result.external_url,
                    "error_code": classification["error_code"] if not result.success else None,
                    "error_message": error_message if not result.success else None,
                    "evidence_path": result.evidence_path,
                    "auto_recoverable": classification["auto_recoverable"] if not result.success else None,
                }
                if not result.success:
                    logger.warning(
                        "publish_failed platform=%s error_code=%s category=%s",
                        platform, classification["error_code"], classification["category"],
                    )
                else:
                    logger.info("publish_success platform=%s url=%s", platform, result.external_url)
                return entry

            except asyncio.TimeoutError:
                logger.warning("publish_timeout platform=%s timeout=%ds", platform, PUBLISH_TIMEOUT_SECONDS)
                return {
                    "success": False, "platform": platform,
                    "error_code": "timeout",
                    "error_message": f"{platform} 게시 {PUBLISH_TIMEOUT_SECONDS}초 타임아웃 초과",
                    "auto_recoverable": True,
                }
            except Exception as e:
                classification = classify_error("publish_exception", str(e))
                logger.error("publish_exception platform=%s error=%s", platform, e)
                return {
                    "success": False, "platform": platform,
                    "error_code": classification["error_code"],
                    "error_message": str(e),
                    "auto_recoverable": classification["auto_recoverable"],
                }

        # 플랫폼별 병렬 게시
        results = await asyncio.gather(*[_publish_one(p) for p in platforms])
        for entry in results:
            publish_results[entry["platform"]] = entry
            if not entry["success"]:
                any_failure = True

        return publish_results, any_failure

    async def publish(self, platform: str, payload: dict) -> PublishResult:
        import sys

        publisher = self.get_publisher(platform)
        account = self.build_account_context(platform)
        package = PlatformPackage(platform=platform, payload=payload)

        # Windows에서 Playwright는 ProactorEventLoop이 필요하지만
        # uvicorn은 SelectorEventLoop을 사용한다.
        # 별도 스레드에서 ProactorEventLoop으로 Playwright를 실행한다.
        if sys.platform == "win32":
            import asyncio
            import concurrent.futures

            def _run_in_proactor():
                loop = asyncio.ProactorEventLoop()
                asyncio.set_event_loop(loop)
                try:
                    return loop.run_until_complete(
                        publisher.publish(package=package, account=account)
                    )
                finally:
                    loop.close()

            loop = asyncio.get_running_loop()
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                result = await loop.run_in_executor(pool, _run_in_proactor)
            return result

        result = await publisher.publish(package=package, account=account)
        return result