"""
에이전트가 자율적으로 선택·호출하는 도구 모음.

LangChain @tool 래핑 버전(lc_ prefix)은 create_react_agent에 bind되어
LLM이 자율적으로 선택합니다.

각 도구는:
1. 명확한 입력/출력 스펙
2. 실패 시 에러 반환 (예외 전파 X)
3. ToolCall 기록을 반환해서 state에 누적 가능
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any, Dict, List, Optional

from langchain_core.tools import tool

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


def _extract_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text).strip()
        text = re.sub(r"```$", "", text).strip()
    try:
        return json.loads(text)
    except Exception:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            return json.loads(m.group(0))
        return {}


# ══════════════════════════════════════════════════════════════════
# LangChain Tool 버전 — create_react_agent에 bind됨
# LLM이 tool_calls를 통해 자율 호출
# ══════════════════════════════════════════════════════════════════

@tool
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


@tool
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


# ══════════════════════════════════════════════════════════════════
# 내부 구현 함수 (직접 호출용 + lc_ 래퍼의 구현체)
# ══════════════════════════════════════════════════════════════════

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
        return _make_tool_call("market_crawl_tool", tool_input, output, success=True)

    except Exception as e:
        logger.error(f"[market_crawl_tool] failed: {e}")
        return _make_tool_call(
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
    Retrieval: 크롤된 매물 데이터 또는 Supabase 벡터 검색
    Augmented Generation: LLM이 데이터를 종합해 가격 추정
    """
    tool_input = {"product": confirmed_product}
    recent_listings = recent_listings or []

    try:
        from app.core.config import settings
        import httpx

        brand = confirmed_product.get("brand", "")
        model = confirmed_product.get("model", "")

        # ── Retrieval ──────────────────────────────────────────────
        # 1순위: 전달받은 크롤 매물 사용
        # 2순위: Supabase 벡터 검색 (테이블 생성 후 활성화)
        retrieved_docs = recent_listings

        if not retrieved_docs:
            # Supabase pgvector 검색 시도 (테이블 미생성 시 fallback)
            try:
                from app.db.supabase_client import get_supabase_client
                supabase = get_supabase_client()
                rows = supabase.table("price_history").select("*").ilike(
                    "model", f"%{model}%"
                ).limit(10).execute()
                retrieved_docs = rows.data or []
            except Exception:
                retrieved_docs = []

        # ── Augmented Generation ───────────────────────────────────
        # LLM이 retrieved_docs를 분석해 가격 추정 생성
        doc_summary = "\n".join([
            f"- {d.get('title', d.get('model', '?'))}: {d.get('price', '?')}원"
            for d in retrieved_docs[:8]
        ]) or "수집된 과거 거래 데이터 없음"

        prompt = f"""다음 중고 거래 데이터를 바탕으로 {brand} {model}의 적정 가격을 추정하라.

참고 데이터:
{doc_summary}

반드시 JSON만 반환:
{{"estimated_price_band": [최저가, 최고가], "rag_summary": "한 줄 요약", "confidence": "high|medium|low"}}

데이터가 없으면 일반 지식 기반으로 추정하고 confidence를 low로 설정."""

        # LLM 호출 (gemini 우선, openai fallback)
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
                    data = resp.json()
                text = data["candidates"][0]["content"]["parts"][0]["text"]
                rag_result = _extract_json(text)
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
                    rag_result = _extract_json(text)
            except Exception as e:
                logger.warning(f"[rag_price] openai failed: {e}")

        output = rag_result or {
            "estimated_price_band": [],
            "rag_summary": f"{brand} {model} 가격 데이터 부족",
            "confidence": "low",
        }
        output["rag_available"] = bool(rag_result)
        output["source_count"] = len(retrieved_docs)

        return _make_tool_call("rag_price_tool", tool_input, output, success=True)

    except Exception as e:
        logger.error(f"[rag_price_tool] failed: {e}")
        return _make_tool_call(
            "rag_price_tool", tool_input,
            {"rag_available": False, "rag_summary": "", "estimated_price_band": [], "confidence": "low"},
            success=False, error=str(e),
        )


# ══════════════════════════════════════════════════════════════════
# LangChain Tool 버전 — Agent 3 (판매글 생성) create_react_agent에 bind됨
# ══════════════════════════════════════════════════════════════════

@tool
async def lc_generate_listing_tool(
    brand: str,
    model: str,
    category: str,
    recommended_price: int,
    image_paths_json: str = "[]",
    platforms_json: str = '["bunjang","joongna"]',
) -> str:
    """
    새 중고거래 판매글(제목, 설명, 태그, 가격)을 LLM으로 생성합니다.
    rewrite_instruction이 없을 때(신규 생성) 반드시 이 툴을 호출하세요.
    반환: JSON {"title": str, "description": str, "tags": [...], "price": int, "images": [...]}
    """
    try:
        import json as _json
        from app.services.listing_service import ListingService

        image_paths = _json.loads(image_paths_json) if image_paths_json else []
        platforms = _json.loads(platforms_json) if platforms_json else ["bunjang", "joongna"]

        confirmed_product = {
            "brand": brand, "model": model, "category": category,
            "confidence": 1.0, "source": "user_input", "storage": "",
        }
        market_context = {
            "median_price": recommended_price,
            "price_band": [],
            "sample_count": 1,
            "crawler_sources": [],
        }
        strategy = {"goal": "fast_sell", "recommended_price": recommended_price}

        svc = ListingService()
        result = await svc.build_canonical_listing(
            confirmed_product=confirmed_product,
            market_context=market_context,
            strategy=strategy,
            image_paths=image_paths,
        )
        if isinstance(result, dict):
            if not result.get("images"):
                result["images"] = image_paths
            return _json.dumps(result, ensure_ascii=False)
        return str(result)

    except Exception as e:
        import json as _json
        return _json.dumps({
            "title": f"{brand} {model} 판매합니다",
            "description": f"{brand} {model} 판매합니다. 상태 양호합니다. 문의 환영합니다.",
            "tags": [t for t in [model, brand, category] if t][:5],
            "price": recommended_price,
            "images": [],
            "error": str(e),
        }, ensure_ascii=False)


@tool
async def lc_rewrite_listing_tool(
    rewrite_instruction: str,
    current_title: str,
    current_description: str,
    current_price: int,
    brand: str,
    model: str,
    category: str,
) -> str:
    """
    사용자의 피드백(rewrite_instruction)을 반영해 기존 판매글을 수정합니다.
    rewrite_instruction이 있을 때 반드시 이 툴을 호출하세요.
    반환: JSON {"title": str, "description": str, "tags": [...], "price": int}
    """
    try:
        import json as _json
        from app.services.listing_service import ListingService

        canonical_listing = {
            "title": current_title,
            "description": current_description,
            "price": current_price,
            "images": [],
            "tags": [model, brand, category],
        }
        confirmed_product = {
            "brand": brand, "model": model, "category": category,
            "confidence": 1.0, "source": "user_input", "storage": "",
        }
        market_context = {
            "median_price": current_price,
            "price_band": [],
            "sample_count": 1,
            "crawler_sources": [],
        }
        strategy = {"goal": "fast_sell", "recommended_price": current_price}

        result = await _rewrite_listing_impl(
            canonical_listing=canonical_listing,
            rewrite_instruction=rewrite_instruction,
            confirmed_product=confirmed_product,
            market_context=market_context,
            strategy=strategy,
        )
        output = result.get("output") or canonical_listing
        if isinstance(output, dict):
            return _json.dumps(output, ensure_ascii=False)
        return str(output)

    except Exception as e:
        import json as _json
        return _json.dumps({
            "title": current_title,
            "description": current_description,
            "price": current_price,
            "tags": [model, brand, category],
            "error": str(e),
        }, ensure_ascii=False)


# ── Tool 3: 판매글 재작성 (내부 구현) ────────────────────────────

async def _rewrite_listing_impl(
    canonical_listing: Dict[str, Any],
    rewrite_instruction: str,
    confirmed_product: Dict[str, Any],
    market_context: Dict[str, Any],
    strategy: Dict[str, Any],
) -> Dict[str, Any]:
    """rewrite_listing_tool 내부 구현 (lc_rewrite_listing_tool과 공유)"""
    tool_input = {"instruction": rewrite_instruction, "current_title": canonical_listing.get("title")}
    try:
        from app.services.listing_service import ListingService

        svc = ListingService()
        image_paths = canonical_listing.get("images", [])

        original_prompt_builder = svc._build_copy_prompt

        def patched_prompt(cp, mc, st, ip, tool_calls_context=""):
            base = original_prompt_builder(cp, mc, st, ip, tool_calls_context)
            return base + f"\n\nUser feedback for rewrite:\n{rewrite_instruction}\nApply this feedback."

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
        return _make_tool_call("rewrite_listing_tool", tool_input, canonical_listing, success=False, error=str(e))


async def rewrite_listing_tool(
    canonical_listing: Dict[str, Any],
    rewrite_instruction: str,
    confirmed_product: Dict[str, Any],
    market_context: Dict[str, Any],
    strategy: Dict[str, Any],
) -> Dict[str, Any]:
    """사용자 피드백 기반 판매글 재작성. 에이전트 3이 rewrite_instruction이 있을 때 호출."""
    return await _rewrite_listing_impl(
        canonical_listing=canonical_listing,
        rewrite_instruction=rewrite_instruction,
        confirmed_product=confirmed_product,
        market_context=market_context,
        strategy=strategy,
    )


# ── Tool 4: Discord 알림 ──────────────────────────────────────────

async def discord_alert_tool(
    message: str,
    session_id: str,
    level: str = "error",
) -> Dict[str, Any]:
    """게시 실패/시스템 이상 시 Discord로 알림. 검증·복구 에이전트가 호출."""
    tool_input = {"message": message, "session_id": session_id, "level": level}
    try:
        import os, httpx
        webhook_url = os.getenv("DISCORD_WEBHOOK_URL")
        if not webhook_url:
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
        return _make_tool_call("discord_alert_tool", tool_input, {"sent": False}, success=False, error=str(e))


# ── Tool 5: 장애 진단 ────────────────────────────────────────────

def diagnose_publish_failure_tool(
    platform: str,
    error_code: str,
    error_message: str,
) -> Dict[str, Any]:
    """게시 실패 원인 분석 및 복구 가능 여부 판단. 검증·복구 에이전트가 호출."""
    tool_input = {"platform": platform, "error_code": error_code, "error_message": error_message}
    msg_lower = (error_message or "").lower()
    code_lower = (error_code or "").lower()

    if any(k in msg_lower for k in ["login", "auth", "session", "credential", "세션"]):
        diagnosis = {"likely_cause": "login_expired", "patch_suggestion": "플랫폼 재로그인 후 세션 파일 갱신 필요", "auto_recoverable": False}
    elif any(k in msg_lower for k in ["timeout", "network", "connection", "refused"]):
        diagnosis = {"likely_cause": "network", "patch_suggestion": "네트워크 재시도 가능", "auto_recoverable": True}
    elif any(k in msg_lower for k in ["content", "policy", "prohibited", "banned"]):
        diagnosis = {"likely_cause": "content_policy", "patch_suggestion": "판매글 내용 검토 필요 (금칙어/정책 위반)", "auto_recoverable": False}
    elif "missing_platform_package" in code_lower:
        diagnosis = {"likely_cause": "missing_package", "patch_suggestion": "prepare-publish 단계를 다시 실행하세요", "auto_recoverable": False}
    else:
        diagnosis = {"likely_cause": "unknown", "patch_suggestion": "로그를 확인하고 수동 처리 필요", "auto_recoverable": False}

    output = {"platform": platform, "error_code": error_code, "error_message": error_message, **diagnosis}
    return _make_tool_call("diagnose_publish_failure_tool", tool_input, output, success=True)


# ── Tool 6: 자동 패치 제안 ───────────────────────────────────────

async def auto_patch_tool(
    platform: str,
    likely_cause: str,
    canonical_listing: Dict[str, Any],
    session_id: str,
) -> Dict[str, Any]:
    """
    게시 실패 원인에 따라 자동 패치 방법을 생성한다. (Agent 4 핵심 툴)

    - login_expired: 세션 갱신 명령어 안내
    - content_policy: LLM으로 대체 제목/설명 자동 생성
    - network: 재시도 전략 반환
    - unknown: 수동 검토 안내
    """
    tool_input = {"platform": platform, "likely_cause": likely_cause, "session_id": session_id}
    try:
        if likely_cause == "login_expired":
            patch = {
                "type": "session_renewal",
                "action": "세션 갱신 필요",
                "command": "python scripts/manual_spikes/save_sessions.py",
                "auto_executable": False,
                "message": f"[{platform}] 로그인 세션이 만료되었습니다. save_sessions.py를 실행해 세션을 갱신하세요.",
            }

        elif likely_cause == "content_policy":
            # LLM으로 대체 콘텐츠 자동 생성
            original_title = canonical_listing.get("title", "")
            original_desc = canonical_listing.get("description", "")

            from app.core.config import settings
            import httpx

            alt_prompt = f"""다음 중고거래 판매글이 플랫폼 정책 위반으로 거절됐습니다.
정책을 준수하는 대안을 작성하세요.

원본 제목: {original_title}
원본 설명: {original_desc[:200]}

규칙:
- 과장 표현 제거
- 금칙어 사용 금지
- 간결하고 사실 기반으로 작성

JSON만 반환: {{"title": "string", "description": "string"}}"""

            alt_content = {}
            if settings.gemini_api_key:
                try:
                    url = (
                        "https://generativelanguage.googleapis.com/v1beta/models/"
                        f"{settings.gemini_listing_model}:generateContent"
                        f"?key={settings.gemini_api_key}"
                    )
                    async with httpx.AsyncClient(timeout=20.0) as client:
                        resp = await client.post(url, json={
                            "contents": [{"parts": [{"text": alt_prompt}]}],
                            "generationConfig": {"temperature": 0.2},
                        })
                        resp.raise_for_status()
                        text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
                        alt_content = _extract_json(text)
                except Exception as e:
                    logger.warning(f"[auto_patch_tool] content rewrite failed: {e}")

            patch = {
                "type": "content_rewrite",
                "action": "판매글 자동 재작성",
                "alternative_title": alt_content.get("title", original_title),
                "alternative_description": alt_content.get("description", original_desc),
                "auto_executable": bool(alt_content),
            }

        elif likely_cause == "network":
            patch = {
                "type": "retry",
                "action": "자동 재시도 예약",
                "retry_after_seconds": 30,
                "auto_executable": True,
                "message": f"[{platform}] 네트워크 오류. 30초 후 자동 재시도합니다.",
            }

        else:
            patch = {
                "type": "manual_review",
                "action": "수동 검토 필요",
                "auto_executable": False,
                "message": f"[{platform}] 자동 처리 불가. 로그를 확인하고 수동으로 처리하세요.",
            }

        return _make_tool_call("auto_patch_tool", tool_input, patch, success=True)

    except Exception as e:
        logger.error(f"[auto_patch_tool] failed: {e}")
        return _make_tool_call(
            "auto_patch_tool", tool_input,
            {"type": "error", "auto_executable": False, "message": str(e)},
            success=False, error=str(e),
        )


# ── Tool 7: 가격 최적화 ──────────────────────────────────────────

async def price_optimization_tool(
    canonical_listing: Dict[str, Any],
    confirmed_product: Dict[str, Any],
    sale_status: str,
    days_listed: int = 7,
) -> Dict[str, Any]:
    """미판매 시 가격 재전략 제안. 판매 후 최적화 에이전트가 호출."""
    tool_input = {
        "sale_status": sale_status,
        "days_listed": days_listed,
        "current_price": canonical_listing.get("price", 0),
    }
    try:
        current_price = int(canonical_listing.get("price", 0) or 0)
        if sale_status != "unsold" or current_price <= 0:
            return _make_tool_call("price_optimization_tool", tool_input, {"suggestion": None}, success=True)

        if days_listed >= 14:
            drop_rate, urgency = 0.10, "high"
        else:
            drop_rate, urgency = 0.05, "medium"

        suggested_price = int(current_price * (1 - drop_rate) // 1000 * 1000)
        output = {
            "type": "price_drop",
            "current_price": current_price,
            "suggested_price": suggested_price,
            "reason": f"{days_listed}일간 미판매 — {int(drop_rate*100)}% 인하 제안",
            "urgency": urgency,
        }
        return _make_tool_call("price_optimization_tool", tool_input, output, success=True)

    except Exception as e:
        return _make_tool_call("price_optimization_tool", tool_input, {"suggestion": None}, success=False, error=str(e))


# ══════════════════════════════════════════════════════════════════
# LangChain Tool 버전 — Agent 4 (복구) create_react_agent에 bind됨
# ══════════════════════════════════════════════════════════════════

@tool
def lc_diagnose_publish_failure_tool(
    platform: str,
    error_code: str,
    error_message: str,
) -> str:
    """
    게시 실패 원인을 분석하고 복구 가능 여부를 판단합니다.
    실패한 각 플랫폼에 대해 반드시 가장 먼저 호출하세요.
    반환: JSON {"likely_cause": str, "patch_suggestion": str, "auto_recoverable": bool}
    """
    result = diagnose_publish_failure_tool(
        platform=platform,
        error_code=error_code,
        error_message=error_message,
    )
    output = result.get("output", {})
    return json.dumps(output, ensure_ascii=False)


@tool
async def lc_auto_patch_tool(
    platform: str,
    likely_cause: str,
    session_id: str,
    current_title: str = "",
    current_description: str = "",
) -> str:
    """
    게시 실패 원인에 따라 자동 패치 방법을 생성합니다.
    lc_diagnose_publish_failure_tool 호출 후 반드시 호출하세요.
    likely_cause 값: login_expired | network | content_policy | unknown
    반환: JSON {"type": str, "action": str, "auto_executable": bool, "message": str}
    """
    canonical_listing = {"title": current_title, "description": current_description}
    result = await auto_patch_tool(
        platform=platform,
        likely_cause=likely_cause,
        canonical_listing=canonical_listing,
        session_id=session_id,
    )
    output = result.get("output", {})
    return json.dumps(output, ensure_ascii=False)


@tool
async def lc_discord_alert_tool(
    message: str,
    session_id: str,
    level: str = "error",
) -> str:
    """
    Discord로 게시 실패 알림을 발송합니다.
    진단과 패치 생성 후 반드시 호출하세요.
    level: error | warning | info
    반환: JSON {"sent": bool}
    """
    result = await discord_alert_tool(
        message=message,
        session_id=session_id,
        level=level,
    )
    output = result.get("output", {})
    return json.dumps(output, ensure_ascii=False)


# ── 하위 호환: 이전 코드에서 직접 호출하는 함수 ──────────────────

async def market_crawl_tool(confirmed_product: Dict[str, Any]) -> Dict[str, Any]:
    """기존 코드 호환용 래퍼"""
    return await _market_crawl_impl(confirmed_product)


async def rag_price_tool(confirmed_product: Dict[str, Any]) -> Dict[str, Any]:
    """기존 코드 호환용 래퍼"""
    return await _rag_price_impl(confirmed_product)
