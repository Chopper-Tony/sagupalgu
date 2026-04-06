-- Publish Job Queue 테이블
-- Supabase SQL Editor에서 실행

CREATE TABLE IF NOT EXISTS publish_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    platform TEXT NOT NULL,  -- bunjang, joongna, daangn
    payload_jsonb JSONB NOT NULL DEFAULT '{}',  -- 플랫폼 패키지 데이터
    status TEXT NOT NULL DEFAULT 'pending',
    attempt_count INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 3,

    -- 워커 lock
    locked_by TEXT,  -- 워커 ID
    locked_at TIMESTAMPTZ,

    -- 타이밍
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    next_retry_at TIMESTAMPTZ,

    -- 결과
    error_code TEXT,
    error_message TEXT,
    evidence_urls_jsonb JSONB DEFAULT '[]',

    -- 제약
    CONSTRAINT valid_status CHECK (
        status IN ('pending', 'claimed', 'running', 'completed', 'failed', 'retry_scheduled', 'cancelled')
    ),
    CONSTRAINT valid_platform CHECK (
        platform IN ('bunjang', 'joongna', 'daangn')
    )
);

-- 인덱스
CREATE INDEX IF NOT EXISTS idx_publish_jobs_status ON publish_jobs(status);
CREATE INDEX IF NOT EXISTS idx_publish_jobs_session ON publish_jobs(session_id);
CREATE INDEX IF NOT EXISTS idx_publish_jobs_user_platform ON publish_jobs(user_id, platform);
CREATE INDEX IF NOT EXISTS idx_publish_jobs_next_retry ON publish_jobs(next_retry_at)
    WHERE status = 'retry_scheduled';
CREATE INDEX IF NOT EXISTS idx_publish_jobs_locked ON publish_jobs(locked_at)
    WHERE status = 'claimed';

-- Per-account lock 지원: 같은 user+platform에 running 상태 1개만 허용
CREATE UNIQUE INDEX IF NOT EXISTS idx_publish_jobs_account_lock
    ON publish_jobs(user_id, platform)
    WHERE status IN ('claimed', 'running');

-- updated_at 자동 갱신 트리거
CREATE OR REPLACE FUNCTION update_publish_jobs_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_publish_jobs_updated_at ON publish_jobs;
CREATE TRIGGER trg_publish_jobs_updated_at
    BEFORE UPDATE ON publish_jobs
    FOR EACH ROW
    EXECUTE FUNCTION update_publish_jobs_updated_at();
