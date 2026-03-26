import { useState, useCallback, useEffect } from "react";
import { AppShell } from "./components/layout/AppShell";
import { SessionSidebar } from "./components/layout/SessionSidebar";
import { ChatWindow } from "./components/chat/ChatWindow";
import { ChatComposer } from "./components/chat/ChatComposer";
import { useSession } from "./hooks/useSession";
import { api } from "./lib/api";
import { getStatusUiConfig, statusLabel } from "./lib/sessionStatusUiMap";
import type { ConfirmedProduct, TimelineItem, TimelineItemInput, SessionStatus } from "./types";

interface SidebarSession {
  id: string;
  lastKnownStatus: SessionStatus;
}
import "./App.css";

let _idCounter = 0;
const nextId = () => String(++_idCounter);

function friendlyError(e: unknown): string {
  const msg = e instanceof Error ? e.message : String(e);
  if (msg.includes("409")) return "이미 처리된 요청입니다. 새 세션을 시작해주세요.";
  if (msg.includes("422")) return "입력값이 올바르지 않습니다. 다시 확인해주세요.";
  if (msg.includes("429") || msg.includes("quota")) return "AI 서비스 이용량을 초과했습니다. 잠시 후 다시 시도해주세요.";
  if (msg.includes("timeout") || msg.includes("ETIMEDOUT")) return "서버 응답이 느립니다. 잠시 후 다시 시도해주세요.";
  if (msg.includes("Network Error") || msg.includes("ECONNREFUSED")) return "네트워크 연결을 확인해주세요.";
  if (msg.includes("502")) return "게시 서버에 연결할 수 없습니다. 잠시 후 다시 시도해주세요.";
  if (msg.includes("500")) return "서버 오류가 발생했습니다. 잠시 후 다시 시도해주세요.";
  if (msg.includes("404")) return "세션을 찾을 수 없습니다. 새 세션을 시작해주세요.";
  // 기술적 메시지는 일반 사용자에게 보여주지 않음
  if (msg.includes("Traceback") || msg.includes("Error:") || msg.includes("Exception"))
    return "처리 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요.";
  return msg;
}

export default function App() {
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
          s.id === activeId ? { ...s, lastKnownStatus: currentStatus } : s
        )
      );
    }
  }, [activeId, currentStatus]);

  const handleNewSession = async () => {
    try {
      const s = await api.createSession();
      setSessions((prev) => [{ id: s.session_id, lastKnownStatus: s.status as SessionStatus }, ...prev]);
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
        pushItem({ type: "progress", status: "product_confirmed", message: "시세를 분석하고 판매글을 생성하고 있습니다..." });
        await api.provideProductInfo(activeId, { model: text });
        const listing = await api.generateListing(activeId);
        setSession(listing);
      } else if (currentStatus === "draft_generated") {
        pushItem({ type: "progress", status: "draft_generated", message: "판매글을 재작성하고 있습니다..." });
        const updated = await api.rewriteListing(activeId, text);
        setSession(updated);
      }
    } catch (e: unknown) {
      pushItem({ type: "error", code: "action_failed", message: friendlyError(e) });
    }
  };

  const handleUploadImages = async (files: File[]) => {
    if (!activeId) return;
    pushItem({ type: "user_message", text: `📷 사진 ${files.length}장을 업로드했습니다` });
    pushItem({ type: "progress", status: "images_uploaded", message: "이미지를 분석하고 있습니다..." });
    try {
      await api.uploadImages(activeId, files);
      // 업로드 후 자동으로 분석 시작
      const analyzed = await api.analyzeSession(activeId);
      setSession(analyzed);
    } catch (e: unknown) {
      pushItem({ type: "error", code: "upload_failed", message: friendlyError(e) });
    }
  };

  const handleAction = async (action: string, payload?: unknown) => {
    if (!activeId) return;
    try {
      switch (action) {
        case "upload_images":
          await handleUploadImages(payload as File[]);
          break;
        case "confirm_product": {
          const product = payload as ConfirmedProduct;
          pushItem({ type: "assistant_message", text: `${product.brand} ${product.model} (${product.category})로 확정했습니다.` });
          pushItem({ type: "progress", status: "product_confirmed", message: "시세를 분석하고 판매글을 생성하고 있습니다..." });
          await api.provideProductInfo(activeId, {
            model: product.model,
            brand: product.brand,
            category: product.category,
          });
          // 확정 후 자동으로 판매글 생성
          const listing = await api.generateListing(activeId);
          setSession(listing);
          break;
        }
        case "prepare_publish": {
          const platforms = payload as string[];
          pushItem({ type: "progress", status: "awaiting_publish_approval", message: "게시를 준비하고 있습니다..." });
          const updated = await api.preparePublish(activeId, platforms);
          setSession(updated);
          break;
        }
        case "rewrite": {
          pushItem({ type: "user_message", text: payload as string });
          pushItem({ type: "progress", status: "draft_generated", message: "판매글을 재작성하고 있습니다..." });
          const updated = await api.rewriteListing(activeId, payload as string);
          setSession(updated);
          break;
        }
        case "publish": {
          pushItem({ type: "progress", status: "publishing", message: "플랫폼에 게시 중입니다..." });
          const updated = await api.publish(activeId);
          setSession(updated);
          break;
        }
        case "edit_draft":
          setLastRenderedStatus("awaiting_publish_approval");
          pushItem({ type: "card", cardType: "DraftCard", status: "draft_generated" });
          break;
        case "update_sale_status":
        case "mark_sold": {
          const updated = await api.updateSaleStatus(activeId, "sold");
          setSession(updated);
          break;
        }
        case "mark_unsold": {
          const updated = await api.updateSaleStatus(activeId, "unsold");
          setSession(updated);
          break;
        }
        case "retry_publish": {
          const updated = await api.publish(activeId);
          setSession(updated);
          break;
        }
        case "restart":
          await handleNewSession();
          break;
      }
    } catch (e: unknown) {
      pushItem({ type: "error", code: action, message: friendlyError(e) });
    }
  };

  const sidebarSessions = sessions.map((s) => ({
    id: s.id,
    label: `판매 세션 ${s.id.slice(0, 8)}`,
    status: statusLabel(s.lastKnownStatus),
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
  );
}
