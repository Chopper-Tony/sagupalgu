"""
Agent 3 툴 — 판매글 생성 + 재작성

툴:
  lc_generate_listing_tool  — create_react_agent에 bind
  lc_rewrite_listing_tool   — create_react_agent에 bind
  rewrite_listing_tool      — 직접 호출용
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict

try:
    from langchain_core.tools import tool as _lc_tool
except ImportError:  # langchain-core 미설치 환경 — _impl 함수는 정상 동작
    def _lc_tool(fn):  # type: ignore[misc]
        return fn

from app.tools._common import _make_tool_call

logger = logging.getLogger(__name__)


# ── LangChain Tool 버전 (create_react_agent bind) ─────────────────

@_lc_tool
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


@_lc_tool
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


# ── 내부 구현 ──────────────────────────────────────────────────────

async def _rewrite_listing_impl(
    canonical_listing: Dict[str, Any],
    rewrite_instruction: str,
    confirmed_product: Dict[str, Any],
    market_context: Dict[str, Any],
    strategy: Dict[str, Any],
) -> Dict[str, Any]:
    """rewrite_listing_tool 내부 구현 (lc_rewrite_listing_tool과 공유).

    ListingService.rewrite_listing()을 통해 처리 —
    monkey patch 없이 공식 extension point 사용.
    """
    tool_input = {"instruction": rewrite_instruction, "current_title": canonical_listing.get("title")}
    try:
        from app.services.listing_service import ListingService

        svc = ListingService()
        result = await svc.rewrite_listing(
            canonical_listing=canonical_listing,
            rewrite_instruction=rewrite_instruction,
            confirmed_product=confirmed_product,
            market_context=market_context,
            strategy=strategy,
        )
        return _make_tool_call("rewrite_listing_tool", tool_input, result, success=True)

    except Exception as e:
        logger.error(f"[rewrite_listing_tool] failed: {e}")
        return _make_tool_call("rewrite_listing_tool", tool_input, canonical_listing, success=False, error=str(e))


# ── 직접 호출용 (하위 호환) ────────────────────────────────────────

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
