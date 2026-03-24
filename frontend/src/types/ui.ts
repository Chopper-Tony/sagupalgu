import type { SessionStatus } from "./session";

// ─────────────────────────────────────────────
// 카드 타입 (각 상태에서 렌더링할 카드)
// ─────────────────────────────────────────────

export type CardType =
  | "ImageUploadCard"
  | "ProgressCard"
  | "ProductConfirmationCard"
  | "DraftCard"
  | "PublishApprovalCard"
  | "PublishResultCard"
  | "SaleStatusCard"
  | "OptimizationSuggestionCard"
  | "ErrorCard";

// ─────────────────────────────────────────────
// ChatComposer 모드
// ─────────────────────────────────────────────

export type ComposerMode =
  | "upload"       // 이미지 업로드 (session_created)
  | "confirmation" // 상품 정보 텍스트 입력 (awaiting_product_confirmation)
  | "rewrite"      // 재작성 지시 입력 (draft_generated)
  | "disabled";    // 입력 불가 (처리 중 / 터미널 상태)

// ─────────────────────────────────────────────
// 상태 → UI 매핑 단위
// ─────────────────────────────────────────────

export interface StatusUiConfig {
  card: CardType;
  composerMode: ComposerMode;
  /** 폴링 활성화 여부 (처리 중 상태만 true) */
  polling: boolean;
  /** 사용자 액션 없이 자동 진행되는 상태 */
  autoProgress: boolean;
}

// ─────────────────────────────────────────────
// 타임라인 아이템 (ChatWindow 렌더링 단위)
// ─────────────────────────────────────────────

export type TimelineItem =
  | { type: "user_message"; text: string; id: string }
  | { type: "assistant_message"; text: string; id: string }
  | { type: "card"; cardType: CardType; status: SessionStatus; id: string }
  | { type: "progress"; status: SessionStatus; message: string; id: string }
  | { type: "error"; code: string; message: string; id: string };

/** pushItem 콜백 인자 타입 — id 없이 각 variant별로 분배 */
export type TimelineItemInput =
  | Omit<Extract<TimelineItem, { type: "user_message" }>, "id">
  | Omit<Extract<TimelineItem, { type: "assistant_message" }>, "id">
  | Omit<Extract<TimelineItem, { type: "card" }>, "id">
  | Omit<Extract<TimelineItem, { type: "progress" }>, "id">
  | Omit<Extract<TimelineItem, { type: "error" }>, "id">;
