import { useEffect, useRef } from "react";
import type { TimelineItem, SessionStatus } from "../../types";
import { ProgressCard } from "../cards/ProgressCard";
import { ErrorCard } from "../cards/ErrorCard";
import "./ChatWindow.css";

interface ChatWindowProps {
  items: TimelineItem[];
  currentStatus: SessionStatus | null;
  /** 카드 액션 콜백 (M17에서 각 카드 컴포넌트 연결 시 사용) */
  onAction?: (action: string, payload?: unknown) => void;
}

export function ChatWindow({ items, currentStatus, onAction }: ChatWindowProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [items]);

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
            return (
              <ProgressCard
                key={item.id}
                status={item.status}
                message={item.message}
              />
            );
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
            // M17에서 각 카드 컴포넌트로 교체
            return (
              <div key={item.id} className="chat-window__card-placeholder">
                [{item.cardType}] — M17 구현 예정
              </div>
            );
          }
          return null;
        })}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
