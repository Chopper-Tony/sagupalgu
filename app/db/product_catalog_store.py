"""
Product Catalog 하이브리드 검색 store (PR4-1).

옵션 D-하이브리드: price_history(외부 크롤) + sell_sessions(자체 sold) 둘 다 활용.
  - sell_sessions 데이터는 catalog_sync_service가 미리 price_history로 normalize 적재
  - 따라서 RAG 시점에는 price_history 한 테이블만 query (단일 source 추상화)
  - source_type 컬럼으로 출처 구분 ('crawled' | 'sell_session' | 'manual')

cold_start 정책:
  - DB에 데이터가 없거나 vector hit 0건이면 cold_start=True 산출
  - LLM이 이를 보면 catalog 결과 신뢰도 낮게 평가하고 clarify로 빠지는 신호로 활용
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from app.db.pgvector_store import EMBEDDING_DIM, get_embedding

logger = logging.getLogger(__name__)


# ── 정규화 보조 ───────────────────────────────────────────────────────
# Vision 결과가 자유 텍스트라 한글↔영문, 공백, 특수문자 변동이 큼.
# query 시점·sync 시점 모두 동일 normalize 함수 통과시켜 검색 일관성 확보.

_BRAND_ALIASES = {
    "애플": "Apple", "apple": "Apple",
    "삼성": "Samsung", "samsung": "Samsung",
    "샤오미": "Xiaomi", "xiaomi": "Xiaomi",
    "엘지": "LG", "lg": "LG",
    "구글": "Google", "google": "Google",
    "소니": "Sony", "sony": "Sony",
}


def normalize_brand(brand: str) -> str:
    """브랜드명 표준화. 변환 사전에 없으면 원본 strip만."""
    if not brand:
        return ""
    key = brand.strip().lower()
    return _BRAND_ALIASES.get(key, brand.strip())


def normalize_model(model: str) -> str:
    """모델명 정규화. 공백 단일화 + strip만 (단순). 추후 sub-model 정규화 확장 여지."""
    if not model:
        return ""
    return " ".join(model.split())


# ── 하이브리드 검색 ────────────────────────────────────────────────────


async def hybrid_search_catalog(
    brand: str,
    model: str,
    category: str,
    api_key: str,
    match_count: int = 10,
    match_threshold: float = 0.35,
) -> Dict[str, Any]:
    """price_history (sessions sync 포함) 단일 테이블에서 하이브리드 검색.

    Returns:
        {
            "matches": [
                {"brand", "model", "category", "title", "price", "platform",
                 "source_type", "similarity"} ...
            ],
            "top_match_confidence": float,    # 가장 유사한 항목의 similarity
            "source_count": int,              # match 개수
            "cold_start": bool,               # vector + keyword 모두 0건이면 True
            "source_breakdown": {             # source_type별 카운트
                "crawled": int, "sell_session": int, "manual": int,
            },
        }
    """
    brand_norm = normalize_brand(brand)
    model_norm = normalize_model(model)

    matches = await _vector_hybrid(brand_norm, model_norm, category, api_key, match_count, match_threshold)

    # vector hit 0건이면 keyword fallback
    if not matches:
        matches = await _keyword_hybrid(brand_norm, model_norm, category, match_count)

    # 결과 정리
    cold_start = len(matches) == 0
    top_conf = max((float(m.get("similarity", 0) or 0) for m in matches), default=0.0)

    breakdown = {"crawled": 0, "sell_session": 0, "manual": 0}
    for m in matches:
        st = m.get("source_type", "crawled")
        if st in breakdown:
            breakdown[st] += 1

    logger.info(
        f"[catalog] hybrid search: matches={len(matches)} top_conf={top_conf:.3f} "
        f"cold_start={cold_start} breakdown={breakdown}"
    )

    return {
        "matches": matches,
        "top_match_confidence": top_conf,
        "source_count": len(matches),
        "cold_start": cold_start,
        "source_breakdown": breakdown,
    }


async def _vector_hybrid(
    brand: str, model: str, category: str, api_key: str,
    match_count: int, match_threshold: float,
) -> List[Dict[str, Any]]:
    """vector_search_catalog_hybrid RPC 호출."""
    from app.db.client import get_supabase

    query_text = " ".join(filter(None, [brand, model, category, "중고"]))
    embedding = await get_embedding(query_text, api_key)
    if not embedding:
        logger.warning("[catalog] embedding 생성 실패 → vector search 스킵")
        return []

    try:
        supabase = get_supabase()
        result = supabase.rpc(
            "vector_search_catalog_hybrid",
            {
                "query_embedding": embedding,
                "match_threshold": match_threshold,
                "match_count": match_count,
            },
        ).execute()
        rows = result.data or []
        return rows
    except Exception as e:
        logger.warning(f"[catalog] vector hybrid RPC 실패: {e}")
        return []


async def _keyword_hybrid(
    brand: str, model: str, category: str, match_count: int,
) -> List[Dict[str, Any]]:
    """keyword_search_catalog_hybrid RPC 호출 (fallback)."""
    from app.db.client import get_supabase

    try:
        supabase = get_supabase()
        result = supabase.rpc(
            "keyword_search_catalog_hybrid",
            {
                "brand_q": brand,
                "model_q": model,
                "category_q": category,
                "match_count": match_count,
            },
        ).execute()
        rows = result.data or []
        return rows
    except Exception as e:
        logger.warning(f"[catalog] keyword hybrid RPC 실패: {e}")
        return []


# ── Sync 보조 ─────────────────────────────────────────────────────────


def session_to_price_history_row(session: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """sell_session 한 행을 price_history 행 dict로 변환. 정규화 적용.

    Returns:
        변환 가능한 경우 dict, 필수 정보 누락 시 None.
    """
    product = (session.get("product_data_jsonb") or {}).get("confirmed_product") or {}
    listing = (session.get("listing_data_jsonb") or {}).get("canonical_listing") or {}

    brand = normalize_brand(product.get("brand", ""))
    model = normalize_model(product.get("model", ""))
    if not model:
        return None  # model 없으면 카탈로그 의미 없음

    price = listing.get("price") or 0
    try:
        price = int(price)
    except (ValueError, TypeError):
        price = 0
    if price <= 0:
        return None  # 가격 없으면 시세 비교 불가

    return {
        "model": model,
        "brand": brand,
        "category": product.get("category", ""),
        "title": listing.get("title", "") or f"{brand} {model}".strip(),
        "price": price,
        "platform": "sagupalgu_market",
        "condition": "sold",
        "source_url": f"session://{session.get('id', '')}",
        "source_type": "sell_session",
    }
