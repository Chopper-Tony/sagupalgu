"""
시세 크롤러 (Market Intelligence Agent 기초)
번개장터 / 중고나라에서 유사 상품 시세 수집

크롤링 방식:
- 번개장터: GraphQL API endpoint 직접 호출 (브라우저 Network 탭에서 확인된 엔드포인트)
- 중고나라: REST API + HTML fallback

사용:
    crawler = MarketCrawler()
    results = await crawler.search("아이폰 15 프로", limit=20)
"""
import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Optional

import aiohttp

logger = logging.getLogger(__name__)


@dataclass
class MarketItem:
    """검색 결과 상품 하나"""
    platform: str
    title: str
    price: int
    condition: str = ""
    url: str = ""
    image_url: str = ""
    sold: bool = False
    created_at: str = ""


@dataclass
class PriceSummary:
    """가격 통계 요약"""
    query: str
    items: list[MarketItem] = field(default_factory=list)

    @property
    def active_items(self):
        return [i for i in self.items if not i.sold]

    @property
    def avg_price(self) -> int:
        prices = [i.price for i in self.active_items if i.price > 0]
        return int(sum(prices) / len(prices)) if prices else 0

    @property
    def min_price(self) -> int:
        prices = [i.price for i in self.active_items if i.price > 0]
        return min(prices) if prices else 0

    @property
    def max_price(self) -> int:
        prices = [i.price for i in self.active_items if i.price > 0]
        return max(prices) if prices else 0

    def recommended_price(self, strategy: str = "normal") -> int:
        """판매 전략별 추천 가격"""
        avg = self.avg_price
        if strategy == "fast":
            return int(avg * 0.90)       # 시세 -10%
        elif strategy == "max_profit":
            return int(avg * 1.05)       # 시세 +5%
        else:
            return avg                    # 시세 그대로

    def __repr__(self):
        return (
            f"PriceSummary('{self.query}') "
            f"avg={self.avg_price:,}원 "
            f"min={self.min_price:,}원 "
            f"max={self.max_price:,}원 "
            f"({len(self.active_items)}개 활성 매물)"
        )


class MarketCrawler:
    """
    번개장터 + 중고나라 시세 수집기
    """

    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "ko-KR,ko;q=0.9",
        "Referer": "https://www.bunjang.co.kr/",
    }

    # ─────────────────────────────────────────
    # 번개장터
    # ─────────────────────────────────────────

    async def _fetch_bunjang(
        self, session: aiohttp.ClientSession, query: str, limit: int = 20
    ) -> list[MarketItem]:
        """
        번개장터 검색 API
        엔드포인트: https://api.bunjang.co.kr/api/1/find_v2.json
        파라미터:
          - q: 검색어
          - n: 결과 수
          - page: 페이지 (0부터)
          - req_ref: search
          - order: score (관련도) / date (최신순)
        """
        url = "https://api.bunjang.co.kr/api/1/find_v2.json"
        params = {
            "q": query,
            "n": limit,
            "page": 0,
            "order": "date",
            "req_ref": "search",
        }

        try:
            async with session.get(url, params=params, headers=self.HEADERS) as resp:
                if resp.status != 200:
                    logger.warning(f"[번개장터] API 응답 {resp.status}")
                    return []

                data = await resp.json(content_type=None)
                items = []

                for raw in data.get("list", []):
                    price_str = str(raw.get("price", "0")).replace(",", "")
                    price = int(price_str) if price_str.isdigit() else 0

                    items.append(MarketItem(
                        platform="번개장터",
                        title=raw.get("name", ""),
                        price=price,
                        condition=raw.get("product_condition_new", ""),
                        url=f"https://www.bunjang.co.kr/products/{raw.get('pid', '')}",
                        image_url=raw.get("image", ""),
                        sold=raw.get("status", "") == "reserved" or raw.get("status") == "sold",
                        created_at=raw.get("update_time", ""),
                    ))

                logger.info(f"[번개장터] '{query}' → {len(items)}개")
                return items

        except Exception as e:
            logger.error(f"[번개장터] 크롤링 실패: {e}")
            return []

    # ─────────────────────────────────────────
    # 중고나라
    # ─────────────────────────────────────────

    async def _fetch_joongna(
        self, session: aiohttp.ClientSession, query: str, limit: int = 20
    ) -> list[MarketItem]:
        """
        중고나라 검색 - 여러 API 엔드포인트 순차 시도 후 HTML fallback
        """
        headers = {
            **self.HEADERS,
            "Referer": "https://web.joongna.com/",
            "Origin": "https://web.joongna.com",
        }
        timeout = aiohttp.ClientTimeout(total=8)

        # __NEXT_DATA__ 에서 확인된 실제 검색 API (get-search-products)
        # POST 방식, web.joongna.com 내부 Next.js API 라우트 사용
        search_payload = {
            "categoryFilter": [{"categoryDepth": 0, "categorySeq": 0}],
            "firstQuantity": limit,
            "jnPayYn": "ALL",
            "keywordSource": "INPUT_KEYWORD",
            "osType": 2,
            "page": 0,
            "parcelFeeYn": "ALL",
            "priceFilter": {"maxPrice": 100000000, "minPrice": 0},
            "quantity": limit,
            "registPeriod": "ALL",
            "saleYn": "SALE_N",
            "sort": "RECOMMEND_SORT",
            "filterTypeCheckoutByUser": False,
            "adjustSearchKeyword": True,
            "searchWord": query,
        }

        content = []
        try:
            post_headers = {
                **headers,
                "Content-Type": "application/json",
            }
            async with session.post(
                "https://web.joongna.com/api/search/products",
                json=search_payload,
                headers=post_headers,
                timeout=timeout,
            ) as resp:
                if resp.status == 200:
                    data = await resp.json(content_type=None)
                    content = (
                        data.get("data", {}).get("content") or
                        data.get("data", {}).get("list") or
                        data.get("content") or
                        data.get("list") or
                        []
                    )
                    if content:
                        logger.info(f"[중고나라] API 성공 (web.joongna.com/api/search/products)")
                logger.debug(f"[중고나라] POST → {resp.status}")
        except Exception as e:
            logger.debug(f"[중고나라] POST 실패: {e}")

        # API 실패 → __NEXT_DATA__ HTML 파싱
        if not content:
            logger.warning("[중고나라] API 실패 → __NEXT_DATA__ fallback")
            return await self._fetch_joongna_html(session, query, limit)

        items = []
        for raw in content[:limit]:
            price_str = str(raw.get("price", "0")).replace(",", "")
            price = int(re.sub(r"\D", "", price_str)) if price_str else 0
            items.append(MarketItem(
                platform="중고나라",
                title=raw.get("subject", raw.get("title", "")),
                price=price,
                condition=raw.get("productCondition", ""),
                url=f"https://web.joongna.com/product/{raw.get('id', '')}",
                image_url=raw.get("thumbnailUrl", ""),
                sold=raw.get("status") in ("SOLD", "RESERVED"),
                created_at=raw.get("createdAt", ""),
            ))

        logger.info(f"[중고나라] '{query}' → {len(items)}개")
        return items

    async def _fetch_joongna_html(
        self, session: aiohttp.ClientSession, query: str, limit: int
    ) -> list[MarketItem]:
        """중고나라 __NEXT_DATA__ 파싱 fallback"""
        try:
            import urllib.parse, json
            encoded_q = urllib.parse.quote(query)
            url = f"https://web.joongna.com/search/{encoded_q}?keywordSource=INPUT_KEYWORD"

            async with session.get(url, headers=self.HEADERS) as resp:
                text = await resp.text()

            from bs4 import BeautifulSoup
            soup = BeautifulSoup(text, "html.parser")
            next_data_tag = soup.find("script", {"id": "__NEXT_DATA__"})
            if not next_data_tag:
                logger.warning("[중고나라 HTML] __NEXT_DATA__ 없음")
                return []

            next_data = json.loads(next_data_tag.string)
            queries = next_data["props"]["pageProps"]["dehydratedState"]["queries"]

            # "get-search-products" 쿼리 찾기
            product_data = []
            for q in queries:
                key = q.get("queryKey", [])
                if key and key[0] == "get-search-products":
                    product_data = (
                        q.get("state", {}).get("data", {}).get("data", {}).get("items") or
                        q.get("state", {}).get("data", {}).get("data", {}).get("content") or
                        q.get("state", {}).get("data", {}).get("items") or
                        []
                    )
                    break

            items = []
            for raw in product_data[:limit]:
                price_str = str(raw.get("price", "0")).replace(",", "")
                price = int(re.sub(r"[^0-9]", "", price_str)) if price_str else 0
                items.append(MarketItem(
                    platform="중고나라",
                    title=raw.get("title", raw.get("subject", "")),
                    price=price,
                    condition=raw.get("productCondition", ""),
                    url=f"https://web.joongna.com/product/{raw.get('seq', raw.get('id', ''))}",
                    image_url=raw.get("url", raw.get("imageUrl", raw.get("thumbnailUrl", ""))),
                    sold=raw.get("state") == 1,
                    created_at=raw.get("sortDate", raw.get("registDate", "")),
                ))

            logger.info(f"[중고나라 HTML] '{query}' → {len(items)}개")
            return items

        except Exception as e:
            logger.error(f"[중고나라 HTML] 실패: {e}")
            return []

    # ─────────────────────────────────────────
    # 통합 검색
    # ─────────────────────────────────────────

    async def search(
        self,
        query: str,
        limit: int = 20,
        platforms: tuple = ("bunjang", "joongna"),
    ) -> PriceSummary:
        """두 플랫폼 동시 검색 후 PriceSummary 반환"""
        async with aiohttp.ClientSession() as session:
            tasks = []
            if "bunjang" in platforms:
                tasks.append(self._fetch_bunjang(session, query, limit))
            if "joongna" in platforms:
                tasks.append(self._fetch_joongna(session, query, limit))

            results = await asyncio.gather(*tasks)

        all_items = []
        for result in results:
            all_items.extend(result)

        summary = PriceSummary(query=query, items=all_items)
        logger.info(f"검색 완료: {summary}")
        return summary