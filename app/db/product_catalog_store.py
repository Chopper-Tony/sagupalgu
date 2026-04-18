"""
Product Catalog 하이브리드 검색 store (PR4-1).

옵션 D-하이브리드: price_history(외부 크롤) + sell_sessions(자체 sold) 둘 다 활용.
  - sell_sessions 데이터는 catalog_sync_service가 미리 price_history로 normalize 적재
  - 따라서 RAG 시점에는 price_history 한 테이블만 query (단일 source 추상화)
  - source_type 컬럼으로 출처 구분 ('crawled' | 'sell_session' | 'manual')

검색 fallback 체인 (CTO PR4-1 리뷰 #2):
  1. vector RPC (vector_search_catalog_hybrid)   — 임베딩 기반 유사도
  2. keyword RPC (keyword_search_catalog_hybrid) — RPC ILIKE
  3. Python ILIKE (.table().ilike())             — RPC 자체가 깨졌을 때 최후
  RPC 실패 = "DB가 RPC 모르는 상태(migration 미적용)" 또는 "Supabase 일시 장애".
  Python ILIKE는 RPC 의존성 0이라 절대 안 깨짐.

cold_start 정책 (CTO PR4-1 리뷰 #4):
  단순 "matches==0"이 아니라 명시 임계값으로 판단:
    - hit count < COLD_START_MIN_HITS (3건 미만)
    - top similarity < COLD_START_MIN_CONFIDENCE (0.5 미만)
  둘 중 하나라도 충족하면 cold_start=True → LLM이 catalog 신뢰도 낮게 평가, clarify로 분기.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from app.db.pgvector_store import EMBEDDING_DIM, get_embedding

logger = logging.getLogger(__name__)


# ── cold_start 임계값 (CTO PR4-1 리뷰 #4) ─────────────────────────────
# LLM이 catalog 결과를 얼마나 신뢰할지 판단하는 명시 기준.
# 둘 중 하나라도 만족 못 하면 cold_start=True (clarify로 분기 신호).
COLD_START_MIN_HITS = 3
COLD_START_MIN_CONFIDENCE = 0.5


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

    Fallback 체인 (CTO PR4-1 #2):
      1. vector RPC → 결과 있으면 사용
      2. keyword RPC (RPC ILIKE)
      3. Python ILIKE (.table().ilike()) — RPC 자체가 깨졌을 때

    Returns:
        {
            "matches": [
                {"brand", "model", "category", "title", "price", "platform",
                 "source_type", "similarity"} ...
            ],
            "top_match_confidence": float,    # 가장 유사한 항목의 similarity
            "source_count": int,              # match 개수
            "cold_start": bool,               # CTO #4: hit < 3건 OR top similarity < 0.5
            "cold_start_reason": Optional[str], # cold_start=True일 때 사유
            "fallback_path": str,             # "vector" | "keyword" | "python_ilike" | "none"
            "source_breakdown": {             # source_type별 카운트
                "crawled": int, "sell_session": int, "manual": int,
            },
        }
    """
    brand_norm = normalize_brand(brand)
    model_norm = normalize_model(model)

    # ── Fallback 체인 ───────────────────────────────────────────
    matches = await _vector_hybrid(brand_norm, model_norm, category, api_key, match_count, match_threshold)
    fallback_path = "vector" if matches else ""

    if not matches:
        matches = await _keyword_hybrid(brand_norm, model_norm, category, match_count)
        if matches:
            fallback_path = "keyword"

    if not matches:
        # CTO #2: RPC 자체가 깨졌을 때(예: migration 005 미적용) 최후 보루.
        matches = await _python_ilike_fallback(brand_norm, model_norm, category, match_count)
        if matches:
            fallback_path = "python_ilike"

    if not matches:
        fallback_path = "none"

    # ── cold_start 산출 (CTO #4: 명시 임계값) ───────────────────
    top_conf = max((float(m.get("similarity", 0) or 0) for m in matches), default=0.0)
    hit_count = len(matches)

    cold_reasons = []
    if hit_count < COLD_START_MIN_HITS:
        cold_reasons.append(f"hit_count={hit_count}<{COLD_START_MIN_HITS}")
    if top_conf < COLD_START_MIN_CONFIDENCE:
        cold_reasons.append(f"top_similarity={top_conf:.3f}<{COLD_START_MIN_CONFIDENCE}")
    cold_start = bool(cold_reasons)
    cold_start_reason = ",".join(cold_reasons) if cold_reasons else None

    breakdown = {"crawled": 0, "sell_session": 0, "manual": 0}
    for m in matches:
        st = m.get("source_type", "crawled")
        if st in breakdown:
            breakdown[st] += 1

    logger.info(
        f"[catalog] hybrid search: matches={hit_count} top_conf={top_conf:.3f} "
        f"cold_start={cold_start} fallback={fallback_path} breakdown={breakdown}"
    )

    return {
        "matches": matches,
        "top_match_confidence": top_conf,
        "source_count": hit_count,
        "cold_start": cold_start,
        "cold_start_reason": cold_start_reason,
        "fallback_path": fallback_path,
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
    """keyword_search_catalog_hybrid RPC 호출 (1차 fallback)."""
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


async def _python_ilike_fallback(
    brand: str, model: str, category: str, match_count: int,
) -> List[Dict[str, Any]]:
    """RPC 자체가 깨졌을 때 (예: migration 005 미적용) 최후 보루 (CTO PR4-1 #2).

    supabase-py의 .table().ilike()로 직접 query. RPC 의존성 0.
    "RPC missing → 시스템 죽음"이 아니라 "RPC missing → 성능은 떨어지지만 결과는 나옴" 보장.
    """
    from app.db.client import get_supabase

    try:
        supabase = get_supabase()
        query = supabase.table("price_history").select(
            "id, brand, model, category, title, price, platform, condition, source_type"
        )
        if model:
            query = query.ilike("model", f"%{model}%")
        if brand:
            query = query.ilike("brand", f"%{brand}%")
        if category:
            query = query.ilike("category", f"%{category}%")

        result = query.order("created_at", desc=True).limit(match_count).execute()
        rows = result.data or []
        if rows:
            logger.info(f"[catalog] python_ilike fallback 성공: {len(rows)}건")
        return rows
    except Exception as e:
        # 진짜 마지막 보루도 실패하면 빈 리스트 — cold_start로 자연 분기
        logger.warning(f"[catalog] python ilike fallback 실패: {e}")
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
