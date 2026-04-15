/**
 * 세션 액션 핸들러 훅 — App.tsx의 handleAction switch를 분리.
 * 각 액션은 API 호출 + 타임라인 아이템 추가 + 세션 상태 업데이트.
 */
import { api } from "../lib/api";
import type { ConfirmedProduct, CanonicalListing, TimelineItemInput, SessionResponse, SessionStatus } from "../types";

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
  if (msg.includes("Traceback") || msg.includes("Error:") || msg.includes("Exception"))
    return "처리 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요.";
  return msg;
}

interface ActionContext {
  activeId: string | null;
  currentStatus: SessionStatus | null;
  pushItem: (item: TimelineItemInput) => void;
  setSession: (s: SessionResponse) => void;
  setLastRenderedStatus: (s: SessionStatus) => void;
  handleNewSession: () => Promise<void>;
  handleUploadImages: (files: File[]) => Promise<void>;
}

export function createActionHandler(ctx: ActionContext) {
  const { activeId, currentStatus, pushItem, setSession, setLastRenderedStatus, handleNewSession, handleUploadImages } = ctx;

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
        pushItem({ type: "card", cardType: "DraftCard", status: "draft_generated" });
      }
    } catch (e: unknown) {
      pushItem({ type: "error", code: "action_failed", message: friendlyError(e) });
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
          pushItem({ type: "assistant_message", text: `${[product.brand, product.model, product.category].filter(Boolean).join(" ")}로 확정했습니다.` });
          pushItem({ type: "progress", status: "product_confirmed", message: "시세를 분석하고 판매글을 생성하고 있습니다..." });
          await api.provideProductInfo(activeId, { model: product.model, brand: product.brand, category: product.category });
          const listing = await api.generateListing(activeId);
          setSession(listing);
          try {
            const tipsResult = await api.getSellerTips(activeId);
            if (tipsResult.tips.length > 0) {
              const tipMessages = tipsResult.tips
                .filter((t) => t.priority !== "low")
                .map((t) => `${t.category === "price" ? "💰" : t.category === "photo" ? "📷" : t.category === "title" ? "✏️" : "💡"} ${t.message}`)
                .join("\n");
              if (tipMessages) pushItem({ type: "assistant_message", text: `판매 팁:\n${tipMessages}` });
            }
          } catch { /* 팁 로드 실패해도 무시 */ }
          break;
        }
        case "prepare_publish": {
          pushItem({ type: "progress", status: "awaiting_publish_approval", message: "게시를 준비하고 있습니다..." });
          const updated = await api.preparePublish(activeId, payload as string[]);
          setSession(updated);
          break;
        }
        case "rewrite": {
          pushItem({ type: "user_message", text: payload as string });
          pushItem({ type: "progress", status: "draft_generated", message: "판매글을 재작성하고 있습니다..." });
          const updated = await api.rewriteListing(activeId, payload as string);
          setSession(updated);
          pushItem({ type: "card", cardType: "DraftCard", status: "draft_generated" });
          break;
        }
        case "publish": {
          pushItem({ type: "progress", status: "publishing", message: "플랫폼에 게시 중입니다..." });
          const updated = await api.publish(activeId);
          setSession(updated);
          break;
        }
        case "direct_edit": {
          const edited = payload as CanonicalListing;
          pushItem({ type: "progress", status: "draft_generated", message: "판매글을 저장하고 있습니다..." });
          const saved = await api.updateListing(activeId, { title: edited.title, description: edited.description, price: edited.price, tags: edited.tags });
          setSession(saved);
          pushItem({ type: "assistant_message", text: `판매글을 직접 수정했습니다.` });
          pushItem({ type: "card", cardType: "DraftCard", status: "draft_generated" });
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

  return { handleSendText, handleAction, friendlyError };
}
