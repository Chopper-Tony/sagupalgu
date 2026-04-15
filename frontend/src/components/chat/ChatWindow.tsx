import { useEffect, useRef } from "react";
import type { TimelineItem, SessionStatus, SessionResponse } from "../../types";
import { ProgressCard } from "../cards/ProgressCard";
import { ErrorCard } from "../cards/ErrorCard";
import { ImageUploadCard } from "../cards/ImageUploadCard";
import { ProductConfirmationCard } from "../cards/ProductConfirmationCard";
import { DraftCard } from "../cards/DraftCard";
import { PublishApprovalCard } from "../cards/PublishApprovalCard";
import { PublishResultCard } from "../cards/PublishResultCard";
import { SaleStatusCard } from "../cards/SaleStatusCard";
import { OptimizationSuggestionCard } from "../cards/OptimizationSuggestionCard";
import "./ChatWindow.css";

interface ChatWindowProps {
  items: TimelineItem[];
  currentStatus: SessionStatus | null;
  session: SessionResponse | null;
  onAction: (action: string, payload?: unknown) => void;
}

export function ChatWindow({ items, currentStatus, session, onAction }: ChatWindowProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  const prevItemsLength = useRef(items.length);

  useEffect(() => {
    const added = items.length > prevItemsLength.current;
    prevItemsLength.current = items.length;
    if (!added && !currentStatus) return;

    // 카드 렌더링 완료 대기 후 최하단 스크롤 (DraftCard 등 큰 컴포넌트 고려)
    const timer = setTimeout(() => {
      bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    }, 300);
    return () => clearTimeout(timer);
  }, [items.length, currentStatus]);

  const renderCard = (item: Extract<TimelineItem, { type: "card" }>) => {
    switch (item.cardType) {
      case "ProgressCard":
        return <ProgressCard status={currentStatus ?? "images_uploaded"} />;

      case "ErrorCard":
        return (
          <ErrorCard
            code=""
            message={session?.last_error ?? "알 수 없는 오류가 발생했습니다."}
            currentStatus={currentStatus}
            onAction={onAction}
          />
        );

      case "ImageUploadCard":
        return (
          <ImageUploadCard
            onUpload={(files) => onAction("upload_images", files)}
          />
        );

      case "ProductConfirmationCard":
        return (
          <ProductConfirmationCard
            candidates={session?.product_candidates ?? []}
            clarificationPrompt={session?.clarification_prompt ?? null}
            onConfirm={(product) => onAction("confirm_product", product)}
          />
        );

      case "DraftCard":
        if (!session?.canonical_listing) return null;
        return (
          <DraftCard
            listing={session.canonical_listing}
            marketContext={session.market_context ?? null}
            criticScore={session.agent_trace?.critic_score ?? null}
            criticFeedback={session.agent_trace?.critic_feedback ?? []}
            toolCalls={session.agent_trace?.tool_calls ?? []}
            decisionRationale={session.agent_trace?.decision_rationale ?? []}
            plan={session.agent_trace?.plan ?? null}
            onApprove={(platforms) => onAction("prepare_publish", platforms)}
            onRewrite={(instruction) => onAction("rewrite", instruction)}
            onDirectEdit={(edited) => onAction("direct_edit", edited)}
          />
        );

      case "PublishApprovalCard":
        if (!session?.canonical_listing) return null;
        return (
          <PublishApprovalCard
            listing={session.canonical_listing}
            platforms={session.selected_platforms ?? []}
            onPublish={() => onAction("publish")}
            onEdit={() => onAction("edit_draft")}
          />
        );

      case "PublishResultCard":
        return (
          <PublishResultCard
            results={session?.platform_results ?? []}
            sessionId={session?.session_id}
            listing={session?.canonical_listing ?? null}
            onUpdateSaleStatus={() => onAction("update_sale_status")}
          />
        );

      case "SaleStatusCard":
        return (
          <SaleStatusCard
            onMarkSold={() => onAction("mark_sold")}
            onMarkUnsold={() => onAction("mark_unsold")}
          />
        );

      case "OptimizationSuggestionCard":
        if (!session?.optimization_suggestion) return null;
        return (
          <OptimizationSuggestionCard
            suggestion={session.optimization_suggestion}
            onRestart={() => onAction("restart")}
          />
        );

      default:
        return (
          <div className="chat-window__card-placeholder">
            [{item.cardType}] — 구현 예정
          </div>
        );
    }
  };

  return (
    <div className="chat-window">
      <div className="chat-window__inner">
        {items.length === 0 && (
          <div className="chat-window__empty">
            <p className="chat-window__empty-title">사구팔구 셀러 코파일럿</p>
            <p className="chat-window__empty-sub">
              사진을 올리면 AI가 상품 분석부터 판매글 작성, 게시까지 도와드립니다.
            </p>
          </div>
        )}

        {items.map((item) => {
          if (item.type === "user_message") {
            return (
              <div key={item.id} className="chat-window__bubble chat-window__bubble--user">
                {item.text}
              </div>
            );
          }
          if (item.type === "assistant_message") {
            return (
              <div key={item.id} className="chat-window__bubble chat-window__bubble--assistant">
                {item.text}
              </div>
            );
          }
          if (item.type === "progress") {
            return <ProgressCard key={item.id} status={item.status} message={item.message} />;
          }
          if (item.type === "error") {
            return (
              <ErrorCard
                key={item.id}
                code={item.code}
                message={item.message}
                currentStatus={currentStatus}
                onAction={onAction}
              />
            );
          }
          if (item.type === "card") {
            return <div key={item.id}>{renderCard(item)}</div>;
          }
          return null;
        })}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
