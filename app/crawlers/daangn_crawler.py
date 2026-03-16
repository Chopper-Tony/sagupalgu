async def daangn_crawler_tool(confirmed_product: dict) -> dict:
    # TODO: 당근 크롤러 spike 코드 연결 위치
    return {
        "source": "daangn",
        "prices": [],
        "sample_count": 0,
        "reason": "spike_not_integrated_yet",
    }


class DaangnCrawler:
    name = "daangn"

    async def search(self, query: str) -> list[dict]:
        # TODO: 에뮬레이터 기반 당근 크롤러 연결 전까지는 빈 결과 반환
        return []