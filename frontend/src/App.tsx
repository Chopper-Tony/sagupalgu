import { useState, useCallback, useEffect } from "react";
import { ThemeToggle } from "./components/ThemeToggle";
import { AppShell } from "./components/layout/AppShell";
import { SessionSidebar } from "./components/layout/SessionSidebar";
import { ChatWindow } from "./components/chat/ChatWindow";
import { ChatComposer } from "./components/chat/ChatComposer";
import { MarketPage } from "./pages/MarketPage";
import { MarketDetailPage } from "./pages/MarketDetailPage";
import { MyListingsPage } from "./pages/MyListingsPage";
import { useSession } from "./hooks/useSession";
import { createActionHandler } from "./hooks/useSessionActions";
import { api } from "./lib/api";
import { getStatusUiConfig, statusLabel } from "./lib/sessionStatusUiMap";
import type { TimelineItem, TimelineItemInput, SessionStatus } from "./types";

interface SidebarSession {
  id: string;
  lastKnownStatus: SessionStatus;
  updatedAt: string;
}
import "./App.css";

let _idCounter = 0;
const nextId = () => String(++_idCounter);

// friendlyError, handleSendText, handleAction은 useSessionActions 훅으로 분리

export default function App() {
  // 해시 라우팅: #/market → 마켓 목록, #/market/{id} → 마켓 상세
  const [page, setPage] = useState<"chat" | "market" | "market-detail" | "my-listings">("chat");
  const [marketDetailId, setMarketDetailId] = useState<string | null>(null);

  useEffect(() => {
    const parseHash = () => {
      const hash = window.location.hash;
      const detailMatch = hash.match(/^#\/market\/(.+)$/);
      if (detailMatch) {
        setPage("market-detail");
        setMarketDetailId(detailMatch[1]);
      } else if (hash === "#/market") {
        setPage("market");
        setMarketDetailId(null);
      } else if (hash === "#/my-listings") {
        setPage("my-listings");
        setMarketDetailId(null);
      } else {
        setPage("chat");
        setMarketDetailId(null);
      }
    };
    parseHash();
    window.addEventListener("hashchange", parseHash);
    return () => window.removeEventListener("hashchange", parseHash);
  }, []);

  const [sessions, setSessions] = useState<SidebarSession[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [timeline, setTimeline] = useState<TimelineItem[]>([]);
  const [lastRenderedStatus, setLastRenderedStatus] = useState<SessionStatus | null>(null);

  const { session, setSession } = useSession(activeId);

  const currentStatus: SessionStatus | null = session?.status ?? null;
  const uiConfig = currentStatus ? getStatusUiConfig(currentStatus) : null;
  const composerMode = uiConfig?.composerMode ?? "disabled";

  const pushItem = useCallback((item: TimelineItemInput) => {
    setTimeline((prev) => {
      // 새 카드나 progress가 들어오면 이전 progress 아이템을 제거
      const filtered = (item.type === "card" || item.type === "progress")
        ? prev.filter((p) => p.type !== "progress")
        : prev;
      return [...filtered, { ...item, id: nextId() } as TimelineItem];
    });
  }, []);

  // 세션 상태 변화 시 카드 아이템 타임라인에 추가
  useEffect(() => {
    if (
      currentStatus &&
      currentStatus !== lastRenderedStatus &&
      uiConfig &&
      !uiConfig.autoProgress
    ) {
      setLastRenderedStatus(currentStatus);
      pushItem({ type: "card", cardType: uiConfig.card, status: currentStatus });
    }
  }, [currentStatus, lastRenderedStatus, uiConfig, pushItem]);

  // 활성 세션 상태 변경 시 사이드바 동기화
  useEffect(() => {
    if (activeId && currentStatus) {
      setSessions((prev) =>
        prev.map((s) =>
          s.id === activeId ? { ...s, lastKnownStatus: currentStatus, updatedAt: new Date().toISOString() } : s
        )
      );
    }
  }, [activeId, currentStatus]);

  const handleNewSession = async () => {
    try {
      const s = await api.createSession();
      setSessions((prev) => [{ id: s.session_id, lastKnownStatus: s.status as SessionStatus, updatedAt: new Date().toISOString() }, ...prev]);
      setActiveId(s.session_id);
      setSession(s);
      setTimeline([]);
      setLastRenderedStatus(null);
    } catch {
      pushItem({ type: "error", code: "create_failed", message: "세션 생성에 실패했습니다." });
    }
  };

  // handleSendText, handleAction은 useSessionActions 훅에서 생성

  const handleUploadImages = async (files: File[]) => {
    let sessionId = activeId;

    // 세션이 없으면 자동 생성 (모바일 UX: + 버튼으로 바로 업로드)
    if (!sessionId) {
      try {
        const s = await api.createSession();
        setSessions((prev) => [{ id: s.session_id, lastKnownStatus: s.status as SessionStatus, updatedAt: new Date().toISOString() }, ...prev]);
        setActiveId(s.session_id);
        setSession(s);
        setTimeline([]);
        setLastRenderedStatus(null);
        sessionId = s.session_id;
      } catch {
        pushItem({ type: "error", code: "create_failed", message: "세션 생성에 실패했습니다." });
        return;
      }
    }

    pushItem({ type: "user_message", text: `📷 사진 ${files.length}장을 업로드했습니다` });
    pushItem({ type: "progress", status: "images_uploaded", message: "이미지를 분석하고 있습니다..." });
    try {
      await api.uploadImages(sessionId, files);
      // 업로드 후 자동으로 분석 시작
      const analyzed = await api.analyzeSession(sessionId);
      setSession(analyzed);
    } catch (e: unknown) {
      pushItem({ type: "error", code: "upload_failed", message: actions.friendlyError(e) });
    }
  };

  const actions = createActionHandler({
    activeId, currentStatus, pushItem, setSession, setLastRenderedStatus, handleNewSession, handleUploadImages,
  });
  const { handleSendText, handleAction } = actions;

  // 마켓/대시보드 페이지는 별도 렌더링
  if (page === "market") return <><ThemeToggle /><MarketPage /></>;
  if (page === "market-detail" && marketDetailId) return <><ThemeToggle /><MarketDetailPage sessionId={marketDetailId} /></>;
  if (page === "my-listings") return <><ThemeToggle /><MyListingsPage /></>;

  const sidebarSessions = sessions.map((s) => ({
    id: s.id,
    label: `판매 세션 ${s.id.slice(0, 8)}`,
    status: statusLabel(s.lastKnownStatus),
  }));

  return (
    <><ThemeToggle />
    <AppShell
      sidebar={
        <SessionSidebar
          sessions={sidebarSessions}
          activeId={activeId}
          onSelect={(id) => { setActiveId(id); setTimeline([]); setLastRenderedStatus(null); }}
          onNew={handleNewSession}
        />
      }
      main={
        <div className="chat-area">
          <ChatWindow
            items={timeline}
            currentStatus={currentStatus}
            session={session}
            onAction={handleAction}
          />
          <ChatComposer
            mode={composerMode}
            onSendText={handleSendText}
            onUploadImages={handleUploadImages}
          />
        </div>
      }
    />
    </>
  );
}
