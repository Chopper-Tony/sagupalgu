import { useState, useEffect, useCallback, useRef } from "react";
import { api } from "../lib/api";
import { isPollingStatus } from "../lib/sessionStatusUiMap";
import type { SessionResponse } from "../types";

const POLLING_INTERVAL_MS = 2500;
const POLLING_INTERVAL_INACTIVE_MS = 10000;

interface UseSessionResult {
  session: SessionResponse | null;
  loading: boolean;
  error: string | null;
  refetch: () => Promise<void>;
  setSession: (s: SessionResponse) => void;
}

export function useSession(sessionId: string | null): UseSessionResult {
  const [session, setSession] = useState<SessionResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const isActiveTab = useRef(true);

  // 탭 활성화 상태 추적
  useEffect(() => {
    const onVisible = () => { isActiveTab.current = document.visibilityState === "visible"; };
    document.addEventListener("visibilitychange", onVisible);
    return () => document.removeEventListener("visibilitychange", onVisible);
  }, []);

  const fetchSession = useCallback(async () => {
    if (!sessionId) return;
    try {
      const data = await api.getSession(sessionId);
      setSession(data);
      setError(null);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "세션을 불러오지 못했습니다");
    }
  }, [sessionId]);

  // 스마트 폴링: 처리 중 상태일 때만 폴링, 탭 비활성 시 간격 늘림
  useEffect(() => {
    if (!sessionId) return;

    const scheduleNext = () => {
      if (timerRef.current) clearTimeout(timerRef.current);

      const shouldPoll = session ? isPollingStatus(session.status) : false;
      if (!shouldPoll) return;

      const interval = isActiveTab.current
        ? POLLING_INTERVAL_MS
        : POLLING_INTERVAL_INACTIVE_MS;

      timerRef.current = setTimeout(async () => {
        await fetchSession();
        scheduleNext();
      }, interval);
    };

    scheduleNext();
    return () => { if (timerRef.current) clearTimeout(timerRef.current); };
  }, [session, sessionId, fetchSession]);

  // 최초 로드
  useEffect(() => {
    if (!sessionId) return;
    setLoading(true);
    fetchSession().finally(() => setLoading(false));
  }, [sessionId, fetchSession]);

  return { session, loading, error, refetch: fetchSession, setSession };
}
