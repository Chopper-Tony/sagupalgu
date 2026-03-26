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
  const sseRef = useRef<EventSource | null>(null);
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

  // SSE 스트림 연결 — 처리 중 상태일 때 자동 시작
  useEffect(() => {
    if (!sessionId || !session) return;
    if (!isPollingStatus(session.status)) return;

    // SSE 연결 시도
    const url = api.getSessionStreamUrl(sessionId);
    const es = new EventSource(url);
    sseRef.current = es;

    es.addEventListener("status_change", (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data) as SessionResponse;
        setSession(data);
        setError(null);
      } catch {
        // JSON 파싱 실패 시 무시
      }
    });

    es.addEventListener("stream_end", () => {
      es.close();
      sseRef.current = null;
    });

    es.onerror = () => {
      // SSE 실패 시 폴링 fallback (아래 useEffect에서 처리)
      es.close();
      sseRef.current = null;
    };

    return () => {
      es.close();
      sseRef.current = null;
    };
  }, [sessionId, session?.status]); // eslint-disable-line react-hooks/exhaustive-deps

  // 폴링 fallback — SSE 연결이 없을 때만 동작
  useEffect(() => {
    if (!sessionId) return;

    const scheduleNext = () => {
      if (timerRef.current) clearTimeout(timerRef.current);

      // SSE 연결이 활성이면 폴링 스킵
      if (sseRef.current && sseRef.current.readyState !== EventSource.CLOSED) return;

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
