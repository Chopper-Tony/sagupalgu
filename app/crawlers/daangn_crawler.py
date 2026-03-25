"""
당근마켓 크롤러 — EXPERIMENTAL (미구현).

당근은 Android 앱 기반이라 웹 크롤링 불가.
향후 uiautomator2 기반 에뮬레이터 크롤링으로 구현 예정.
현재는 빈 결과를 반환하며, 시세 분석은 번장/중고나라 데이터만 사용.
"""
import logging

logger = logging.getLogger(__name__)


async def daangn_crawler_tool(confirmed_product: dict) -> dict:
    """[EXPERIMENTAL] 당근 시세 크롤러 — 미구현, 빈 결과 반환."""
    logger.info("daangn_crawler: experimental stub — 빈 결과 반환")
    return {
        "source": "daangn",
        "prices": [],
        "sample_count": 0,
        "reason": "experimental_not_implemented",
    }


class DaangnCrawler:
    """[EXPERIMENTAL] 당근마켓 크롤러 — 미구현."""
    name = "daangn"

    async def search(self, query: str) -> list[dict]:
        logger.info("DaangnCrawler.search: experimental stub query='%s'", query)
        return []
