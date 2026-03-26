import type { SessionStatus, StatusUiConfig } from "../types";

// ─────────────────────────────────────────────
// 상태 → UI 매핑 테이블
// docs/api-contract.md 와 1:1 대응.
// 카드 추가/변경 시 이 파일 한 곳만 수정.
// ─────────────────────────────────────────────

export const SESSION_STATUS_UI_MAP: Record<SessionStatus, StatusUiConfig> = {
  session_created: {
    card: "ImageUploadCard",
    composerMode: "upload",
    polling: false,
    autoProgress: false,
  },
  images_uploaded: {
    card: "ProgressCard",
    composerMode: "disabled",
    polling: true,
    autoProgress: true,
  },
  awaiting_product_confirmation: {
    card: "ProductConfirmationCard",
    composerMode: "confirmation",
    polling: false,
    autoProgress: false,
  },
  market_analyzing: {
    card: "ProgressCard",
    composerMode: "disabled",
    polling: true,
    autoProgress: true,
  },
  product_confirmed: {
    card: "ProgressCard",
    composerMode: "disabled",
    polling: true,
    autoProgress: true,
  },
  draft_generated: {
    card: "DraftCard",
    composerMode: "rewrite",
    polling: false,
    autoProgress: false,
  },
  awaiting_publish_approval: {
    card: "PublishApprovalCard",
    composerMode: "disabled",
    polling: false,
    autoProgress: false,
  },
  publishing: {
    card: "ProgressCard",
    composerMode: "disabled",
    polling: true,
    autoProgress: true,
  },
  completed: {
    card: "PublishResultCard",
    composerMode: "disabled",
    polling: false,
    autoProgress: false,
  },
  awaiting_sale_status_update: {
    card: "SaleStatusCard",
    composerMode: "disabled",
    polling: false,
    autoProgress: false,
  },
  optimization_suggested: {
    card: "OptimizationSuggestionCard",
    composerMode: "disabled",
    polling: false,
    autoProgress: false,
  },
  publishing_failed: {
    card: "ErrorCard",
    composerMode: "disabled",
    polling: false,
    autoProgress: false,
  },
  failed: {
    card: "ErrorCard",
    composerMode: "disabled",
    polling: false,
    autoProgress: false,
  },
};

export function getStatusUiConfig(status: SessionStatus): StatusUiConfig {
  return SESSION_STATUS_UI_MAP[status];
}

/** 폴링이 필요한 상태인지 (처리 중 상태) */
export function isPollingStatus(status: SessionStatus): boolean {
  return SESSION_STATUS_UI_MAP[status].polling;
}

/** 터미널 상태인지 */
export function isTerminalStatus(status: SessionStatus): boolean {
  return (
    status === "optimization_suggested" ||
    status === "failed"
  );
}

// ─────────────────────────────────────────────
// 플랫폼 영문 → 한글 매핑
// ─────────────────────────────────────────────

const PLATFORM_LABEL: Record<string, string> = {
  bunjang: "번개장터",
  joongna: "중고나라",
  daangn: "당근마켓",
};

/** 플랫폼 영문 코드를 한글 이름으로 변환. 매핑 없으면 원본 반환. */
export function platformLabel(code: string): string {
  return PLATFORM_LABEL[code] ?? code;
}

// ─────────────────────────────────────────────
// ProgressCard 상태별 카피
// ─────────────────────────────────────────────

export const PROGRESS_COPY: Partial<Record<SessionStatus, { title: string; subtitle: string }>> = {
  images_uploaded: {
    title: "상품을 분석하고 있습니다",
    subtitle: "잠시만 기다려 주세요",
  },
  market_analyzing: {
    title: "중고 시세를 분석 중입니다",
    subtitle: "비슷한 상품의 거래 데이터를 수집하고 있습니다",
  },
  product_confirmed: {
    title: "판매 전략을 수립하고 있습니다",
    subtitle: "잠시만 기다려 주세요",
  },
  publishing: {
    title: "플랫폼에 게시 중입니다",
    subtitle: "선택한 플랫폼에 판매글을 올리고 있습니다",
  },
};
