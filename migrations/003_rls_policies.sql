-- 003: Row Level Security 활성화
-- 실행일: 2026-04-09
-- Supabase 보안 경고 대응 (rls_disabled_in_public, sensitive_columns_exposed)

-- sell_sessions RLS
ALTER TABLE sell_sessions ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Service role full access" ON sell_sessions
  FOR ALL USING (auth.role() = 'service_role');

CREATE POLICY "Users access own sessions" ON sell_sessions
  FOR ALL USING (auth.uid()::text = user_id);

-- publish_jobs RLS
ALTER TABLE publish_jobs ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Service role full access" ON publish_jobs
  FOR ALL USING (auth.role() = 'service_role');

CREATE POLICY "Users access own jobs" ON publish_jobs
  FOR ALL USING (auth.uid()::text = user_id);

-- Function search_path 경고 해결
ALTER FUNCTION public.update_publish_jobs_updated_at() SET search_path = public;
