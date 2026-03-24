import { useState, useCallback } from "react";
import { AppShell } from "./components/layout/AppShell";
import { SessionSidebar } from "./components/layout/SessionSidebar";
import { ChatWindow } from "./components/chat/ChatWindow";
import { ChatComposer } from "./components/chat/ChatComposer";
import { useSession } from "./hooks/useSession";
import { api } from "./lib/api";
import { getStatusUiConfig } from "./lib/sessionStatusUiMap";
import type { TimelineItem, TimelineItemInput, SessionStatus } from "./types";
import "./App.css";

let _idCounter = 0;
const nextId = () => String(++_idCounter);

export default function App() {
  const [sessionIds, setSessionIds] = useState<string[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [timeline, setTimeline] = useState<TimelineItem[]>([]);
  const [lastRenderedStatus, setLastRenderedStatus] = useState<SessionStatus | null>(null);

  const { session, setSession } = useSession(activeId);

  const currentStatus: SessionStatus | null = session?.status ?? null;
  const uiConfig = currentStatus ? getStatusUiConfig(currentStatus) : null;
  const composerMode = uiConfig?.composerMode ?? "disabled";

  const pushItem = useCallback((item: TimelineItemInput) => {
    setTimeline((prev) => [...prev, { ...item, id: nextId() } as TimelineItem]);
  }, []);

  // 세션 상태 변화 시 카드 아이템 타임라인에 추가
  if (
    currentStatus &&
    currentStatus !== lastRenderedStatus &&
    uiConfig &&
    !uiConfig.autoProgress
  ) {
    setLastRenderedStatus(currentStatus);
    pushItem({ type: "card", cardType: uiConfig.card, status: currentStatus });
  }

  const handleNewSession = async () => {
    try {
      const s = await api.createSession();
      setSessionIds((prev) => [s.session_id, ...prev]);
      setActiveId(s.session_id);
      setSession(s);
      setTimeline([]);
      setLastRenderedStatus(null);
    } catch {
      pushItem({ type: "error", code: "create_failed", message: "세션 생성에 실패했습니다." });
    }
  };

  const handleSendText = async (text: string) => {
    if (!activeId || !currentStatus) return;
    pushItem({ type: "user_message", text });

    try {
      if (currentStatus === "awaiting_product_confirmation") {
        const updated = await api.provideProductInfo(activeId, { user_input: text });
        setSession(updated);
      } else if (currentStatus === "draft_generated") {
        pushItem({ type: "progress", status: "draft_generated", message: "판매글을 재작성하고 있습니다..." });
        const updated = await api.generateListing(activeId, text);
        setSession(updated);
      }
    } catch (e: unknown) {
      pushItem({ type: "error", code: "action_failed", message: e instanceof Error ? e.message : "요청에 실패했습니다." });
    }
  };

  const handleUploadImages = async (files: File[]) => {
    if (!activeId) return;
    pushItem({ type: "user_message", text: `📷 사진 ${files.length}장을 업로드했습니다` });
    pushItem({ type: "progress", status: "images_uploaded", message: "이미지를 분석하고 있습니다..." });
    try {
      const updated = await api.uploadImages(activeId, files);
      setSession(updated);
    } catch (e: unknown) {
      pushItem({ type: "error", code: "upload_failed", message: e instanceof Error ? e.message : "업로드에 실패했습니다." });
    }
  };

  const handleAction = async (action: string) => {
    if (!activeId) return;
    if (action === "restart") {
      await handleNewSession();
    } else if (action === "retry_publish") {
      try {
        const updated = await api.publish(activeId);
        setSession(updated);
      } catch (e: unknown) {
        pushItem({ type: "error", code: "publish_failed", message: e instanceof Error ? e.message : "게시에 실패했습니다." });
      }
    }
  };

  const sidebarSessions = sessionIds.map((id) => ({
    id,
    label: `판매 세션 ${id.slice(0, 8)}`,
    status: id === activeId ? (currentStatus ?? "생성됨") : "완료",
  }));

  return (
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
  );
}
