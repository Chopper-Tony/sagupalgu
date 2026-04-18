-- ════════════════════════════════════════════════════════════════
-- Migration 005: Product Catalog 하이브리드 RAG 인프라 (PR4-1)
--
-- 목적:
--   PR4 Product Identity 승격을 위한 카탈로그 RAG 데이터 layer.
--   price_history(외부 크롤 데이터) + sell_sessions(자체 마켓 sold 데이터) 하이브리드 검색.
--
-- 변경:
--   1. price_history에 source_type 컬럼 추가 (price_history sync 계열 추적용).
--   2. 신규 RPC vector_search_catalog_hybrid: pgvector 유사도 + brand/model 매칭.
--      sold sessions에서 sync된 행은 source_type='sell_session', 외부 크롤은 'crawled'.
--   3. 신규 RPC keyword_search_catalog_hybrid: ILIKE fallback.
--
-- 적용 방법:
--   1. Supabase 대시보드 → SQL Editor → 본 SQL 전체 실행.
--   2. python scripts/cron/sync_catalog.py --dry-run 으로 sync 시뮬레이션 확인.
--   3. python scripts/cron/sync_catalog.py 로 첫 batch 실행.
-- ════════════════════════════════════════════════════════════════

-- ── 1. price_history.source_type 컬럼 추가 ───────────────────────
-- 'crawled' (외부 크롤, 기존 데이터 default) | 'sell_session' (PR4-1 sync로 추가된 자체 데이터)
-- 'manual' (수동 입력 등 미래 확장용)
ALTER TABLE price_history
    ADD COLUMN IF NOT EXISTS source_type TEXT NOT NULL DEFAULT 'crawled';

-- 기존 데이터(385건)는 모두 외부 크롤이므로 'crawled' 유지.
UPDATE price_history SET source_type = 'crawled' WHERE source_type IS NULL OR source_type = '';

-- source_type 별 검색 필터링용 인덱스
CREATE INDEX IF NOT EXISTS price_history_source_type_idx ON price_history (source_type);

-- sync 중복 방지용 unique-ish 인덱스 (source_type='sell_session' + source_url 조합)
-- source_url에는 sync 시 sell_session id를 'session://{uuid}' 형태로 기록.
CREATE INDEX IF NOT EXISTS price_history_source_url_idx ON price_history (source_url)
    WHERE source_url IS NOT NULL AND source_url != '';


-- ── 2. 하이브리드 벡터 검색 RPC ───────────────────────────────────
-- price_history 단일 테이블 안에서 source_type 무관하게 검색.
-- sold sessions 데이터는 sync_catalog.py가 미리 price_history로 normalize 해서 적재해둠.
-- 따라서 RPC 자체는 단일 테이블 query로 단순화 (LLM이 단일 source 추상화로 받음).
CREATE OR REPLACE FUNCTION vector_search_catalog_hybrid(
    query_embedding VECTOR(1536),
    match_threshold FLOAT DEFAULT 0.35,
    match_count     INT   DEFAULT 10
)
RETURNS TABLE (
    id           UUID,
    model        TEXT,
    brand        TEXT,
    category     TEXT,
    title        TEXT,
    price        INTEGER,
    platform     TEXT,
    condition    TEXT,
    source_type  TEXT,
    similarity   FLOAT
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT
        ph.id,
        ph.model,
        ph.brand,
        ph.category,
        ph.title,
        ph.price,
        ph.platform,
        ph.condition,
        ph.source_type,
        1 - (ph.embedding <=> query_embedding) AS similarity
    FROM price_history ph
    WHERE ph.embedding IS NOT NULL
      AND 1 - (ph.embedding <=> query_embedding) > match_threshold
    ORDER BY ph.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;


-- ── 3. 키워드 검색 RPC (ILIKE fallback) ──────────────────────────
-- 임베딩 생성 실패 또는 vector hit 0건일 때 사용.
CREATE OR REPLACE FUNCTION keyword_search_catalog_hybrid(
    brand_q       TEXT DEFAULT '',
    model_q       TEXT DEFAULT '',
    category_q    TEXT DEFAULT '',
    match_count   INT  DEFAULT 10
)
RETURNS TABLE (
    id           UUID,
    model        TEXT,
    brand        TEXT,
    category     TEXT,
    title        TEXT,
    price        INTEGER,
    platform     TEXT,
    condition    TEXT,
    source_type  TEXT
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT
        ph.id, ph.model, ph.brand, ph.category, ph.title,
        ph.price, ph.platform, ph.condition, ph.source_type
    FROM price_history ph
    WHERE (model_q = '' OR ph.model ILIKE '%' || model_q || '%')
      AND (brand_q = '' OR ph.brand ILIKE '%' || brand_q || '%')
      AND (category_q = '' OR ph.category ILIKE '%' || category_q || '%')
    ORDER BY ph.created_at DESC
    LIMIT match_count;
END;
$$;


-- ── 4. Sync cursor (incremental sync 용) ─────────────────────────
-- 마지막 sync 시점을 기록해서 cron 재실행 시 신규 sold sessions만 처리.
CREATE TABLE IF NOT EXISTS catalog_sync_cursor (
    id              SMALLINT PRIMARY KEY DEFAULT 1,
    last_synced_at  TIMESTAMPTZ NOT NULL DEFAULT '1970-01-01T00:00:00Z',
    last_run_count  INT NOT NULL DEFAULT 0,
    last_run_at     TIMESTAMPTZ,
    CONSTRAINT catalog_sync_cursor_singleton CHECK (id = 1)
);

-- 단일 행 보장 (없으면 생성)
INSERT INTO catalog_sync_cursor (id) VALUES (1)
ON CONFLICT (id) DO NOTHING;
