"""
에이전트가 자율적으로 선택·호출하는 도구 모음.

각 도구는:
1. 명확한 입력/출력 스펙
2. 실패 시 에러 반환 (예외 전파 X)
3. ToolCall 기록을 반환해서 state에 누적 가능
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ── 공통 헬퍼 ──────────────────────────────────────────────────────

def _make_tool_call(
    tool_name: str,
    input_data: Dict[str, Any],
    output: Any,
    success: bool,
    error: Optional[str] = None,
) -> Dict[str, Any]:
    return {
        "tool_name": tool_name,
        "input": input_data,
        "output": output,
        "success": success,
        "error": error,
    }


# ── Tool 1: 시세 수집 도구 ──────────────────────────────────────────

async def market_crawl_tool(confirmed_product: Dict[str, Any]) -> Dict[str, Any]:
    """
    번개장터 + 중고나라에서 시세 수집.
    에이전트가 confirmed_product가 있을 때 선택적으로 호출.
    """
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

        for query in queries[:3]:  # 상위 3개 쿼리만
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
                logger.warning(f"[market_crawl_tool] query={query} failed: {e}")
                continue

        price_context = PriceAggregator.aggregate(all_listings)
        output = {
            **price_context,
            "crawler_sources": crawler_sources,
        }
        return _make_tool_call("market_crawl_tool", tool_input, output, success=True)

    except Exception as e:
        logger.error(f"[market_crawl_tool] failed: {e}")
        return _make_tool_call(
            "market_crawl_tool", tool_input,
            {"median_price": None, "price_band": None, "sample_count": 0, "crawler_sources": []},
            success=False, error=str(e),
        )


# ── Tool 2: RAG 가격 검색 도구 ──────────────────────────────────────

async def rag_price_tool(confirmed_product: Dict[str, Any]) -> Dict[str, Any]:
    """
    과거 거래 데이터 기반 RAG 검색.
    크롤러 결과가 부족할 때 에이전트가 보완적으로 호출.
    """
    tool_input = {"product": confirmed_product}
    try:
        # TODO: 실제 벡터 DB 연결 시 교체
        # 지금은 크롤러 결과를 보완하는 더미 구현
        model = confirmed_product.get("model", "")
        brand = confirmed_product.get("brand", "")
        rag_summary = f"{brand} {model} 최근 거래 기준 시세 참고값".strip()

        output = {
            "rag_available": False,  # 실제 구현 전까지 False
            "rag_summary": rag_summary,
            "rag_price_hint": None,
        }
        return _make_tool_call("rag_price_tool", tool_input, output, success=True)

    except Exception as e:
        return _make_tool_call(
            "rag_price_tool", tool_input,
            {"rag_available": False, "rag_summary": "", "rag_price_hint": None},
            success=False, error=str(e),
        )


# ── Tool 3: 판매글 재작성 도구 ──────────────────────────────────────

async def rewrite_listing_tool(
    canonical_listing: Dict[str, Any],
    rewrite_instruction: str,
    confirmed_product: Dict[str, Any],
    market_context: Dict[str, Any],
    strategy: Dict[str, Any],
) -> Dict[str, Any]:
    """
    사용자 피드백 기반 판매글 재작성.
    에이전트 3이 rewrite_instruction이 있을 때 호출.
    """
    tool_input = {
        "instruction": rewrite_instruction,
        "current_title": canonical_listing.get("title"),
    }
    try:
        from app.services.listing_service import ListingService

        svc = ListingService()
        image_paths = canonical_listing.get("images", [])

        # rewrite_instruction을 프롬프트에 반영
        original_prompt_builder = svc._build_copy_prompt

        def patched_prompt(cp, mc, st, ip):
            base = original_prompt_builder(cp, mc, st, ip)
            return base + f"\n\nUser feedback for rewrite:\n{rewrite_instruction}\nApply this feedback to improve the listing."

        svc._build_copy_prompt = patched_prompt

        result = await svc.build_canonical_listing(
            confirmed_product=confirmed_product,
            market_context=market_context,
            strategy=strategy,
            image_paths=image_paths,
        )

        return _make_tool_call("rewrite_listing_tool", tool_input, result, success=True)

    except Exception as e:
        logger.error(f"[rewrite_listing_tool] failed: {e}")
        return _make_tool_call(
            "rewrite_listing_tool", tool_input, canonical_listing,
            success=False, error=str(e),
        )


# ── Tool 4: Discord 알림 도구 ──────────────────────────────────────

async def discord_alert_tool(
    message: str,
    session_id: str,
    level: str = "error",
) -> Dict[str, Any]:
    """
    게시 실패 / 시스템 이상 시 Discord로 알림.
    검증·복구 에이전트가 호출.
    """
    tool_input = {"message": message, "session_id": session_id, "level": level}
    try:
        import os, httpx
        webhook_url = os.getenv("DISCORD_WEBHOOK_URL")
        if not webhook_url:
            logger.warning("[discord_alert_tool] DISCORD_WEBHOOK_URL not set, skipping")
            return _make_tool_call("discord_alert_tool", tool_input, {"sent": False}, success=True)

        color = {"error": 0xFF0000, "warning": 0xFFA500, "info": 0x00BFFF}.get(level, 0xFF0000)
        payload = {
            "embeds": [{
                "title": f"[사구팔구] {level.upper()}",
                "description": message,
                "color": color,
                "fields": [{"name": "session_id", "value": session_id, "inline": True}],
            }]
        }

        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(webhook_url, json=payload)
            resp.raise_for_status()

        return _make_tool_call("discord_alert_tool", tool_input, {"sent": True}, success=True)

    except Exception as e:
        logger.error(f"[discord_alert_tool] failed: {e}")
        return _make_tool_call(
            "discord_alert_tool", tool_input, {"sent": False},
            success=False, error=str(e),
        )


# ── Tool 5: 장애 진단 도구 ──────────────────────────────────────────

def diagnose_publish_failure_tool(
    platform: str,
    error_code: str,
    error_message: str,
) -> Dict[str, Any]:
    """
    게시 실패 원인 분석 및 복구 가능 여부 판단.
    검증·복구 에이전트가 호출.
    """
    tool_input = {"platform": platform, "error_code": error_code, "error_message": error_message}

    # 규칙 기반 진단
    msg_lower = (error_message or "").lower()
    code_lower = (error_code or "").lower()

    if any(k in msg_lower for k in ["login", "auth", "session", "credential"]):
        diagnosis = {
            "likely_cause": "login_expired",
            "patch_suggestion": "플랫폼 재로그인 후 세션 파일 갱신 필요",
            "auto_recoverable": False,
        }
    elif any(k in msg_lower for k in ["timeout", "network", "connection", "refused"]):
        diagnosis = {
            "likely_cause": "network",
            "patch_suggestion": "네트워크 재시도 가능",
            "auto_recoverable": True,
        }
    elif any(k in msg_lower for k in ["content", "policy", "prohibited", "banned"]):
        diagnosis = {
            "likely_cause": "content_policy",
            "patch_suggestion": "판매글 내용 검토 필요 (금칙어/정책 위반 가능성)",
            "auto_recoverable": False,
        }
    elif "missing_platform_package" in code_lower:
        diagnosis = {
            "likely_cause": "missing_package",
            "patch_suggestion": "prepare-publish 단계를 다시 실행하세요",
            "auto_recoverable": False,
        }
    else:
        diagnosis = {
            "likely_cause": "unknown",
            "patch_suggestion": "로그를 확인하고 수동 처리 필요",
            "auto_recoverable": False,
        }

    output = {
        "platform": platform,
        "error_code": error_code,
        "error_message": error_message,
        **diagnosis,
    }
    return _make_tool_call("diagnose_publish_failure_tool", tool_input, output, success=True)


# ── Tool 6: 가격 최적화 도구 ──────────────────────────────────────

async def price_optimization_tool(
    canonical_listing: Dict[str, Any],
    confirmed_product: Dict[str, Any],
    sale_status: str,
    days_listed: int = 7,
) -> Dict[str, Any]:
    """
    미판매 시 가격 재전략 제안.
    판매 후 최적화 에이전트가 호출.
    """
    tool_input = {
        "sale_status": sale_status,
        "days_listed": days_listed,
        "current_price": canonical_listing.get("price", 0),
    }
    try:
        current_price = int(canonical_listing.get("price", 0) or 0)

        if sale_status != "unsold" or current_price <= 0:
            return _make_tool_call(
                "price_optimization_tool", tool_input,
                {"suggestion": None}, success=True,
            )

        # 7일 미판매 → -5%, 14일 이상 → -10%
        if days_listed >= 14:
            drop_rate = 0.10
            urgency = "high"
        else:
            drop_rate = 0.05
            urgency = "medium"

        suggested_price = int(current_price * (1 - drop_rate) // 1000 * 1000)  # 천원 단위 내림

        output = {
            "type": "price_drop",
            "current_price": current_price,
            "suggested_price": suggested_price,
            "reason": f"{days_listed}일간 미판매 — 시세 대비 {int(drop_rate*100)}% 인하 제안",
            "urgency": urgency,
        }
        return _make_tool_call("price_optimization_tool", tool_input, output, success=True)

    except Exception as e:
        return _make_tool_call(
            "price_optimization_tool", tool_input, {"suggestion": None},
            success=False, error=str(e),
        )
