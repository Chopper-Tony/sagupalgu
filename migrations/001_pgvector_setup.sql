-- ════════════════════════════════════════════════════════════════
-- Migration 001: pgvector 확장 및 price_history 테이블 생성
--
-- 적용 방법:
--   1. Supabase 대시보드 → SQL Editor → New query
--   2. 아래 SQL 전체 붙여넣기 후 Run
--   3. python scripts/setup_pgvector.py 실행 (초기 데이터 시딩)
-- ════════════════════════════════════════════════════════════════

-- pgvector 확장 활성화
CREATE EXTENSION IF NOT EXISTS vector;

-- 가격 이력 테이블
CREATE TABLE IF NOT EXISTS price_history (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    model        TEXT NOT NULL,
    brand        TEXT NOT NULL DEFAULT '',
    category     TEXT NOT NULL DEFAULT '',
    title        TEXT NOT NULL DEFAULT '',
    price        INTEGER NOT NULL,
    platform     TEXT NOT NULL DEFAULT '',
    condition    TEXT DEFAULT 'unknown',
    source_url   TEXT DEFAULT '',
    embedding    VECTOR(1536),       -- OpenAI text-embedding-3-small
    created_at   TIMESTAMPTZ DEFAULT NOW()
);

-- 벡터 유사도 검색 인덱스 (IVFFlat - 대용량 최적)
CREATE INDEX IF NOT EXISTS price_history_embedding_idx
    ON price_history USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

-- 키워드 검색 보조 인덱스
CREATE INDEX IF NOT EXISTS price_history_model_idx  ON price_history (model);
CREATE INDEX IF NOT EXISTS price_history_brand_idx  ON price_history (brand);
CREATE INDEX IF NOT EXISTS price_history_platform_idx ON price_history (platform);

-- ── 벡터 유사도 검색 RPC 함수 ─────────────────────────────────
CREATE OR REPLACE FUNCTION search_price_history(
    query_embedding VECTOR(1536),
    match_threshold FLOAT DEFAULT 0.4,
    match_count     INT   DEFAULT 10
)
RETURNS TABLE (
    id          UUID,
    model       TEXT,
    brand       TEXT,
    category    TEXT,
    title       TEXT,
    price       INTEGER,
    platform    TEXT,
    condition   TEXT,
    similarity  FLOAT
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
        1 - (ph.embedding <=> query_embedding) AS similarity
    FROM price_history ph
    WHERE embedding IS NOT NULL
      AND 1 - (ph.embedding <=> query_embedding) > match_threshold
    ORDER BY ph.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;
