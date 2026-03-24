"""
Agent 2 툴 — 시세 크롤링 + RAG 가격 조회

툴:
  lc_market_crawl_tool  — create_react_agent에 bind
  lc_rag_price_tool     — create_react_agent에 bind
  market_crawl_tool     — 직접 호출용 래퍼
  rag_price_tool        — 직접 호출용 래퍼
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List

try:
    from langchain_core.tools import tool as _lc_tool
except ImportError:  # langchain-core 미설치 환경 — _impl 함수는 정상 동작
    def _lc_tool(fn):  # type: ignore[misc]
        return fn

from app.tools._common import extract_json, make_tool_call

logger = logging.getLogger(__name__)


# ── LangChain Tool 버전 (create_react_agent bind) ─────────────────

@_lc_tool
async def lc_market_crawl_tool(brand: str, model: str, category: str) -> str:
    """
    번개장터·중고나라에서 중고 시세를 실시간 크롤링합니다.
    현재 활성 매물의 가격, 시세 범위, 표본 수를 반환합니다.
    항상 가장 먼저 호출해야 합니다.
    반환: JSON {"median_price": int, "price_band": [low, high], "sample_count": int, "crawler_sources": [...]}
    """
    confirmed_product = {"brand": brand, "model": model, "category": category}
    result = await _market_crawl_impl(confirmed_product)
    output = result.get("output", {})
    return json.dumps(output, ensure_ascii=False)


@_lc_tool
async def lc_rag_price_tool(brand: str, model: str, recent_listings_json: str = "") -> str:
    """
    과거 거래 기록 기반 RAG로 가격 참고값을 조회합니다.
    크롤 표본(sample_count)이 3개 미만일 때 반드시 호출해서 가격 추정을 보완하세요.
    recent_listings_json: market_crawl_tool에서 받은 매물 데이터 (없으면 빈 문자열)
    반환: JSON {"rag_summary": str, "estimated_price_band": [low, high], "confidence": str}
    """
    confirmed_product = {"brand": brand, "model": model}
    recent_listings = []
    if recent_listings_json:
        try:
            recent_listings = json.loads(recent_listings_json)
        except Exception:
            pass
    result = await _rag_price_impl(confirmed_product, recent_listings)
    output = result.get("output", {})
    return json.dumps(output, ensure_ascii=False)


# ── 내부 구현 ──────────────────────────────────────────────────────

async def _market_crawl_impl(confirmed_product: Dict[str, Any]) -> Dict[str, Any]:
    """시세 크롤링 실제 구현"""
    tool_input = {"product": confirmed_product}
    try:
        from app.crawlers.market_crawler import MarketCrawler
        from app.services.market.query_builder import QueryBuilder
        from app.services.market.relevance_scorer import RelevanceScorer
        from app.services.market.price_aggregator import PriceAggregator

        queries = QueryBuilder.build_queries(confirmed_product)
        crawler = MarketCrawler()

        all_listings = []
        crawler_sources = []

        for query in queries[:3]:
            try:
                summary = await crawler.search(query, limit=20)
                for item in summary.active_items:
                    listing = {
                        "title": item.title,
                        "price": item.price,
                        "platform": item.platform,
                        "url": item.url,
                    }
                    score = RelevanceScorer.score(confirmed_product, listing)
                    if score >= 0.3:
                        all_listings.append(listing)
                        if item.platform not in crawler_sources:
                            crawler_sources.append(item.platform)
            except Exception as e:
                logger.warning(f"[market_crawl] query={query} failed: {e}")
                continue

        price_context = PriceAggregator.aggregate(all_listings)
        output = {**price_context, "crawler_sources": crawler_sources, "raw_listings": all_listings[:10]}
        return make_tool_call("market_crawl_tool", tool_input, output, success=True)

    except Exception as e:
        logger.error(f"[market_crawl_tool] failed: {e}")
        return make_tool_call(
            "market_crawl_tool", tool_input,
            {"median_price": None, "price_band": None, "sample_count": 0, "crawler_sources": [], "raw_listings": []},
            success=False, error=str(e),
        )


async def _rag_price_impl(
    confirmed_product: Dict[str, Any],
    recent_listings: List[Dict] = None,
) -> Dict[str, Any]:
    """
    RAG 가격 조회 실제 구현.

    Retrieval 우선순위:
      1. 전달받은 크롤 매물 (recent_listings)
      2. Supabase pgvector 코사인 유사도 검색 (search_price_history RPC)
      3. Supabase 키워드(ILIKE) 검색 (pgvector RPC 실패 시)

    Augmented Generation:
      LLM(Gemini → OpenAI)이 retrieved_docs를 분석해 가격 추정 생성
    """
    tool_input = {"product": confirmed_product}
    recent_listings = recent_listings or []

    try:
        from app.core.config import settings
        import httpx

        brand = confirmed_product.get("brand", "")
        model = confirmed_product.get("model", "")

        # ── Retrieval ──────────────────────────────────────────────
        retrieved_docs: List[Dict] = list(recent_listings)
        retrieval_source = "crawl" if retrieved_docs else "none"

        if not retrieved_docs:
            # 1순위: pgvector 코사인 유사도 검색
            try:
                from app.db.pgvector_store import vector_search_price_history, is_table_ready

                if await is_table_ready() and settings.openai_api_key:
                    rows = await vector_search_price_history(
                        brand=brand,
                        model=model,
                        api_key=settings.openai_api_key,
                        match_count=10,
                        match_threshold=0.4,
                    )
                    if rows:
                        retrieved_docs = rows
                        retrieval_source = "pgvector"
                        logger.info(f"[rag_price] pgvector: {len(rows)}건 검색됨")
            except Exception as e:
                logger.warning(f"[rag_price] pgvector search failed: {e}")

        if not retrieved_docs:
            # 2순위: 키워드 기반 검색 (fallback)
            try:
                from app.db.pgvector_store import keyword_search_price_history
                rows = await keyword_search_price_history(model=model, brand=brand, limit=10)
                if rows:
                    retrieved_docs = rows
                    retrieval_source = "keyword"
                    logger.info(f"[rag_price] keyword: {len(rows)}건 검색됨")
            except Exception as e:
                logger.warning(f"[rag_price] keyword search failed: {e}")

        # ── Augmented Generation ───────────────────────────────────
        doc_summary = "\n".join([
            f"- {d.get('title', d.get('model', '?'))}: {d.get('price', '?')}원 ({d.get('platform', '?')})"
            for d in retrieved_docs[:8]
        ]) or "수집된 과거 거래 데이터 없음"

        confidence_hint = "high" if len(retrieved_docs) >= 5 else ("medium" if retrieved_docs else "low")

        prompt = f"""다음 중고 거래 데이터를 바탕으로 {brand} {model}의 적정 가격을 추정하라.

참고 데이터 ({retrieval_source}, {len(retrieved_docs)}건):
{doc_summary}

반드시 JSON만 반환:
{{"estimated_price_band": [최저가, 최고가], "rag_summary": "한 줄 요약", "confidence": "{confidence_hint}"}}

데이터가 없으면 일반 지식 기반으로 추정하고 confidence를 low로 설정."""

        rag_result = None

        if settings.gemini_api_key:
            try:
                url = (
                    "https://generativelanguage.googleapis.com/v1beta/models/"
                    f"{settings.gemini_listing_model}:generateContent"
                    f"?key={settings.gemini_api_key}"
                )
                async with httpx.AsyncClient(timeout=30.0) as client:
                    resp = await client.post(url, json={
                        "contents": [{"parts": [{"text": prompt}]}],
                        "generationConfig": {"temperature": 0.1},
                    })
                    resp.raise_for_status()
                    text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
                rag_result = extract_json(text)
            except Exception as e:
                logger.warning(f"[rag_price] gemini failed: {e}")

        if not rag_result and settings.openai_api_key:
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    resp = await client.post(
                        "https://api.openai.com/v1/chat/completions",
                        headers={"Authorization": f"Bearer {settings.openai_api_key}"},
                        json={
                            "model": settings.openai_listing_model,
                            "messages": [{"role": "user", "content": prompt}],
                            "temperature": 0.1,
                        },
                    )
                    resp.raise_for_status()
                    text = resp.json()["choices"][0]["message"]["content"]
                    rag_result = extract_json(text)
            except Exception as e:
                logger.warning(f"[rag_price] openai failed: {e}")

        output = rag_result or {
            "estimated_price_band": [],
            "rag_summary": f"{brand} {model} 가격 데이터 부족",
            "confidence": "low",
        }
        output["rag_available"] = bool(rag_result)
        output["source_count"] = len(retrieved_docs)
        output["retrieval_source"] = retrieval_source

        return make_tool_call("rag_price_tool", tool_input, output, success=True)

    except Exception as e:
        logger.error(f"[rag_price_tool] failed: {e}")
        return make_tool_call(
            "rag_price_tool", tool_input,
            {"rag_available": False, "rag_summary": "", "estimated_price_band": [], "confidence": "low"},
            success=False, error=str(e),
        )


# ── 직접 호출용 래퍼 (하위 호환) ──────────────────────────────────

async def market_crawl_tool(confirmed_product: Dict[str, Any]) -> Dict[str, Any]:
    """기존 코드 호환용 래퍼"""
    return await _market_crawl_impl(confirmed_product)


async def rag_price_tool(confirmed_product: Dict[str, Any]) -> Dict[str, Any]:
    """기존 코드 호환용 래퍼"""
    return await _rag_price_impl(confirmed_product)
