"""
Catalog Sync Service (PR4-1).

sell_sessions(status='completed', sale_status='sold')를 price_history로 incremental sync.
cron이 일 1회 실행. 옵션 D-하이브리드의 self-reinforcing 부분.

설계:
  - catalog_sync_cursor 테이블에 마지막 sync 시점 기록 → incremental
  - 한 번 실행 = batch (max_batch 한도 안에서 최신 sold sessions 처리)
  - source_url='session://{uuid}'로 중복 방지 (이미 sync된 session은 skip)
  - 임베딩 생성은 OpenAI text-embedding-3-small (pgvector_store.get_embedding 재사용)

cursor 사용 이유:
  - 매 실행마다 전체 sold sessions 재조회하면 OpenAI embedding 비용 폭주
  - cursor로 신규 분만 가져오면 일 1회 실행도 충분
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# 한 번 실행 시 처리하는 최대 sessions 수. OpenAI rate limit + cost 보호.
# 1000건 이상 누적되면 여러 번 실행하면 됨 (cursor가 진행 위치 기억).
DEFAULT_MAX_BATCH = 200


async def sync_completed_sessions_to_price_history(
    api_key: str,
    max_batch: int = DEFAULT_MAX_BATCH,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """sold sessions를 price_history로 sync.

    Args:
        api_key: OpenAI API key (임베딩 생성용)
        max_batch: 한 번에 처리할 최대 session 수
        dry_run: True면 실제 insert 없이 시뮬레이션만

    Returns:
        {
            "fetched": int,        # cursor 이후 sold sessions 수
            "transformable": int,  # price_history 행으로 변환 가능한 수
            "skipped_duplicate": int,  # 이미 sync된 (source_url 중복) 수
            "inserted": int,       # 실제 insert한 수
            "cursor_advanced_to": str,  # 새 cursor 시점 (ISO datetime)
            "dry_run": bool,
        }
    """
    from app.db.client import get_supabase
    from app.db.pgvector_store import insert_price_records
    from app.db.product_catalog_store import session_to_price_history_row

    supabase = get_supabase()

    # ── 1. 현재 cursor 읽기 ──────────────────────────────────────
    cursor_at = await _read_cursor(supabase)
    logger.info(f"[catalog_sync] starting cursor={cursor_at} max_batch={max_batch} dry_run={dry_run}")

    # ── 2. cursor 이후 sold sessions 조회 (updated_at 기준 정렬) ──
    # JSONB path 필터는 PostgREST 문법 사용:
    #   listing_data_jsonb->canonical_listing->>sale_status = 'sold'
    try:
        resp = (
            supabase.table("sell_sessions")
            .select("id, product_data_jsonb, listing_data_jsonb, updated_at")
            .eq("status", "completed")
            .filter(
                "listing_data_jsonb->canonical_listing->>sale_status",
                "eq",
                "sold",
            )
            .gt("updated_at", cursor_at)
            .order("updated_at")
            .limit(max_batch)
            .execute()
        )
        sessions = resp.data or []
    except Exception as e:
        logger.error(f"[catalog_sync] sessions 조회 실패: {e}")
        return _empty_result(cursor_at, dry_run)

    fetched = len(sessions)
    logger.info(f"[catalog_sync] fetched={fetched} sessions since cursor")

    if fetched == 0:
        await _write_cursor_meta(supabase, cursor_at, 0, dry_run=dry_run)
        return _empty_result(cursor_at, dry_run)

    # ── 3. 각 session을 price_history 행으로 변환 ────────────────
    rows: List[Dict[str, Any]] = []
    skipped_unconvertible = 0
    for s in sessions:
        row = session_to_price_history_row(s)
        if row is None:
            skipped_unconvertible += 1
            continue
        rows.append(row)
    transformable = len(rows)
    logger.info(f"[catalog_sync] transformable={transformable} (skipped_unconvertible={skipped_unconvertible})")

    # ── 4. 중복 체크 (source_url='session://{id}' 이미 있는 경우 skip) ──
    if rows:
        source_urls = [r["source_url"] for r in rows]
        try:
            existing_resp = (
                supabase.table("price_history")
                .select("source_url")
                .in_("source_url", source_urls)
                .execute()
            )
            existing_urls = {r["source_url"] for r in (existing_resp.data or [])}
        except Exception as e:
            logger.warning(f"[catalog_sync] 중복 체크 실패 (전부 insert 시도): {e}")
            existing_urls = set()
    else:
        existing_urls = set()

    new_rows = [r for r in rows if r["source_url"] not in existing_urls]
    skipped_duplicate = len(rows) - len(new_rows)
    logger.info(f"[catalog_sync] new={len(new_rows)} skipped_duplicate={skipped_duplicate}")

    # ── 5. 실제 insert (dry_run이면 skip) ────────────────────────
    inserted = 0
    if not dry_run and new_rows:
        inserted = await insert_price_records(new_rows, api_key=api_key)
    elif dry_run:
        logger.info(f"[catalog_sync] dry_run → would insert {len(new_rows)} rows")
        inserted = 0

    # ── 6. cursor 업데이트 (마지막 session의 updated_at으로) ────
    new_cursor = sessions[-1]["updated_at"] if sessions else cursor_at
    await _write_cursor_meta(supabase, new_cursor, inserted, dry_run=dry_run)

    return {
        "fetched": fetched,
        "transformable": transformable,
        "skipped_unconvertible": skipped_unconvertible,
        "skipped_duplicate": skipped_duplicate,
        "inserted": inserted,
        "cursor_advanced_to": new_cursor,
        "dry_run": dry_run,
    }


# ── Cursor I/O ────────────────────────────────────────────────────────


async def _read_cursor(supabase) -> str:
    """catalog_sync_cursor에서 last_synced_at 읽기. 없으면 epoch."""
    try:
        resp = supabase.table("catalog_sync_cursor").select("last_synced_at").eq("id", 1).execute()
        rows = resp.data or []
        if rows and rows[0].get("last_synced_at"):
            return rows[0]["last_synced_at"]
    except Exception as e:
        logger.warning(f"[catalog_sync] cursor 읽기 실패 → epoch 사용: {e}")
    return "1970-01-01T00:00:00+00:00"


async def _write_cursor_meta(supabase, new_cursor: str, run_count: int, dry_run: bool) -> None:
    """catalog_sync_cursor 업데이트 (last_synced_at + last_run_*)."""
    if dry_run:
        logger.info(f"[catalog_sync] dry_run → cursor write skipped (would set to {new_cursor})")
        return
    try:
        now = datetime.now(timezone.utc).isoformat()
        supabase.table("catalog_sync_cursor").update({
            "last_synced_at": new_cursor,
            "last_run_count": run_count,
            "last_run_at": now,
        }).eq("id", 1).execute()
    except Exception as e:
        logger.warning(f"[catalog_sync] cursor 업데이트 실패: {e}")


def _empty_result(cursor_at: str, dry_run: bool) -> Dict[str, Any]:
    return {
        "fetched": 0,
        "transformable": 0,
        "skipped_unconvertible": 0,
        "skipped_duplicate": 0,
        "inserted": 0,
        "cursor_advanced_to": cursor_at,
        "dry_run": dry_run,
    }
