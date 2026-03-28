"""
pgvector 기반 가격 이력 벡터 스토어.

- 임베딩: OpenAI text-embedding-3-small (1536 dims)
- 저장소: Supabase PostgreSQL + pgvector extension
- 검색: cosine similarity via search_price_history RPC
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

EMBEDDING_DIM = 1536
EMBEDDING_MODEL = "text-embedding-3-small"


async def get_embedding(text: str, api_key: str) -> Optional[List[float]]:
    """OpenAI text-embedding-3-small로 텍스트 임베딩 생성."""
    try:
        import httpx
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                "https://api.openai.com/v1/embeddings",
                headers={"Authorization": f"Bearer {api_key}"},
                json={"model": EMBEDDING_MODEL, "input": text},
            )
            resp.raise_for_status()
            return resp.json()["data"][0]["embedding"]
    except (ValueError, TypeError, KeyError) as e:
        logger.warning(f"[pgvector] embedding response parse failed: {e}")
        return None
    except Exception as e:
        logger.warning(f"[pgvector] embedding failed: {e}")
        return None


async def vector_search_price_history(
    brand: str,
    model: str,
    api_key: str,
    match_count: int = 10,
    match_threshold: float = 0.4,
) -> List[Dict[str, Any]]:
    """
    pgvector 코사인 유사도 검색으로 가격 이력 조회.
    search_price_history RPC 함수를 호출한다.

    Returns:
        [{"model", "brand", "price", "platform", "title", "similarity"}, ...]
    """
    from app.db.client import get_supabase

    query_text = f"{brand} {model} 중고"
    embedding = await get_embedding(query_text, api_key)
    if not embedding:
        logger.warning("[pgvector] embedding 생성 실패 — vector search 불가")
        return []

    try:
        supabase = get_supabase()
        result = supabase.rpc(
            "search_price_history",
            {
                "query_embedding": embedding,
                "match_threshold": match_threshold,
                "match_count": match_count,
            },
        ).execute()
        rows = result.data or []
        logger.info(f"[pgvector] vector search: {len(rows)}건 ({brand} {model})")
        return rows
    except (ValueError, TypeError, KeyError) as e:
        logger.warning(f"[pgvector] vector search 데이터 처리 실패: {e}")
        return []
    except Exception as e:
        logger.warning(f"[pgvector] vector search RPC 실패: {e}")
        return []


async def keyword_search_price_history(
    model: str,
    brand: str = "",
    limit: int = 10,
) -> List[Dict[str, Any]]:
    """벡터 검색 실패 시 대안: 키워드(ILIKE) 기반 검색."""
    from app.db.client import get_supabase

    try:
        supabase = get_supabase()
        query = supabase.table("price_history").select("*").ilike("model", f"%{model}%")
        if brand:
            query = query.ilike("brand", f"%{brand}%")
        result = query.order("created_at", desc=True).limit(limit).execute()
        rows = result.data or []
        logger.info(f"[pgvector] keyword search: {len(rows)}건 ({brand} {model})")
        return rows
    except (ValueError, TypeError, KeyError) as e:
        logger.warning(f"[pgvector] keyword search 데이터 처리 실패: {e}")
        return []
    except Exception as e:
        logger.warning(f"[pgvector] keyword search 실패: {e}")
        return []


async def insert_price_records(
    records: List[Dict[str, Any]],
    api_key: str,
    skip_embedding: bool = False,
) -> int:
    """
    가격 이력 레코드를 임베딩과 함께 삽입.

    Args:
        records: [{"model", "brand", "category", "title", "price", "platform", ...}]
        api_key: OpenAI API key for embedding
        skip_embedding: True면 embedding 없이 삽입 (키워드 검색만 가능)

    Returns:
        삽입된 레코드 수
    """
    from app.db.client import get_supabase

    supabase = get_supabase()
    inserted = 0

    for record in records:
        try:
            embedding = None
            if not skip_embedding:
                text = " ".join(filter(None, [
                    record.get("brand", ""),
                    record.get("model", ""),
                    record.get("title", ""),
                    record.get("category", ""),
                ]))
                embedding = await get_embedding(text.strip(), api_key)

            row = {
                "model": record.get("model", ""),
                "brand": record.get("brand", ""),
                "category": record.get("category", ""),
                "title": record.get("title", ""),
                "price": int(record.get("price", 0) or 0),
                "platform": record.get("platform", ""),
                "condition": record.get("condition", "unknown"),
                "source_url": record.get("url", record.get("source_url", "")),
            }
            if embedding:
                row["embedding"] = embedding

            supabase.table("price_history").insert(row).execute()
            inserted += 1
        except (ValueError, TypeError, KeyError) as e:
            logger.warning(f"[pgvector] insert 데이터 변환 실패 ({record.get('model')}): {e}")
            continue
        except Exception as e:
            logger.warning(f"[pgvector] insert 실패 ({record.get('model')}): {e}")
            continue

    logger.info(f"[pgvector] {inserted}/{len(records)}건 삽입 완료")
    return inserted


async def is_table_ready() -> bool:
    """price_history 테이블이 존재하고 사용 가능한지 확인."""
    from app.db.client import get_supabase
    try:
        supabase = get_supabase()
        supabase.table("price_history").select("id").limit(1).execute()
        return True
    except Exception as e:
        logger.debug("[pgvector] table readiness check failed: %s", e)
        return False
