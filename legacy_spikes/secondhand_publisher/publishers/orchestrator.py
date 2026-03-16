"""
멀티 플랫폼 동시 게시 오케스트레이터
LangGraph Router에서 호출하는 최상위 인터페이스
"""
import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from ..core.models import ListingPackage, PublishResult, Platform
from .bunjang import BunjangPublisher
from .joongna import JoongnaPublisher

logger = logging.getLogger(__name__)


@dataclass
class PlatformCredentials:
    """플랫폼별 로그인 정보"""
    bunjang_phone: Optional[str] = None
    bunjang_password: Optional[str] = None
    joongna_id: Optional[str] = None        # 네이버 ID or 자체 계정
    joongna_password: Optional[str] = None


class PublisherOrchestrator:
    """
    여러 플랫폼에 동시 또는 순차 게시하는 오케스트레이터
    
    사용 예:
        orchestrator = PublisherOrchestrator(credentials, headless=True)
        results = await orchestrator.publish_all(package)
    """

    def __init__(
        self,
        credentials: PlatformCredentials,
        headless: bool = True,
        session_dir: Path = Path("./sessions"),
        screenshot_dir: Path = Path("./screenshots"),
        concurrent: bool = False,   # True면 두 플랫폼 동시 게시 (리소스 주의)
    ):
        self.credentials = credentials
        self.concurrent = concurrent

        # 각 Publisher 인스턴스 생성
        self.publishers = {
            Platform.BUNJANG: BunjangPublisher(
                session_dir=session_dir,
                screenshot_dir=screenshot_dir,
                headless=headless,
            ),
            Platform.JOONGNA: JoongnaPublisher(
                session_dir=session_dir,
                screenshot_dir=screenshot_dir,
                headless=headless,
            ),
        }

    async def publish_all(
        self,
        package: ListingPackage,
        platforms: Optional[list[Platform]] = None,
    ) -> dict[Platform, PublishResult]:
        """
        지정된 모든 플랫폼에 게시
        platforms=None 이면 credentials가 있는 모든 플랫폼에 게시
        """
        if platforms is None:
            platforms = self._available_platforms()

        logger.info(f"게시 시작: {[p.value for p in platforms]}")

        if self.concurrent:
            results = await self._publish_concurrent(package, platforms)
        else:
            results = await self._publish_sequential(package, platforms)

        # 결과 요약 로깅
        for platform, result in results.items():
            logger.info(str(result))

        return results

    async def _publish_sequential(
        self, package: ListingPackage, platforms: list[Platform]
    ) -> dict[Platform, PublishResult]:
        """순차 게시 (안전, 기본값)"""
        results = {}
        for platform in platforms:
            phone, password = self._get_credentials(platform)
            publisher = self.publishers[platform]
            result = await publisher.run(package, phone, password)
            results[platform] = result
            if not result.success:
                logger.warning(f"{platform.value} 게시 실패 - 다음 플랫폼으로 계속")
        return results

    async def _publish_concurrent(
        self, package: ListingPackage, platforms: list[Platform]
    ) -> dict[Platform, PublishResult]:
        """동시 게시 (빠르지만 메모리/CPU 사용 2배)"""
        async def _run(platform):
            phone, password = self._get_credentials(platform)
            publisher = self.publishers[platform]
            result = await publisher.run(package, phone, password)
            return platform, result

        tasks = [_run(p) for p in platforms]
        results_list = await asyncio.gather(*tasks, return_exceptions=True)

        results = {}
        for item in results_list:
            if isinstance(item, Exception):
                logger.error(f"동시 게시 중 오류: {item}")
            else:
                platform, result = item
                results[platform] = result
        return results

    def _available_platforms(self) -> list[Platform]:
        platforms = []
        if self.credentials.bunjang_phone and self.credentials.bunjang_password:
            platforms.append(Platform.BUNJANG)
        if self.credentials.joongna_id and self.credentials.joongna_password:
            platforms.append(Platform.JOONGNA)
        return platforms

    def _get_credentials(self, platform: Platform) -> tuple[str, str]:
        if platform == Platform.BUNJANG:
            return self.credentials.bunjang_phone, self.credentials.bunjang_password
        elif platform == Platform.JOONGNA:
            return self.credentials.joongna_id, self.credentials.joongna_password
        raise ValueError(f"Unknown platform: {platform}")
