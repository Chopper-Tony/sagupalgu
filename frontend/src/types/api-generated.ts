// ⚠️ 자동 생성 파일 — 직접 수정 금지
// 생성: python scripts/generate_api_types.py
// 소스: FastAPI OpenAPI 스키마 (SessionUIResponse)

// ── SessionStatus ──────────────────────────────────────

export type SessionStatusGenerated =
  | "awaiting_product_confirmation"
  | "awaiting_publish_approval"
  | "awaiting_sale_status_update"
  | "completed"
  | "draft_generated"
  | "failed"
  | "images_uploaded"
  | "market_analyzing"
  | "optimization_suggested"
  | "product_confirmed"
  | "publishing"
  | "publishing_failed"
  | "session_created";

// ── SessionResponse (평탄화 필드만) ────────────────────

export interface SessionResponseGenerated {
  session_id: string;
  status: string;
  checkpoint?: string | null;
  next_action?: string | null;
  needs_user_input?: boolean;
  clarification_prompt?: string | null;
  image_urls?: string[];
  product_candidates?: Record<string, any>[];
  confirmed_product?: Record<string, any> | null;
  canonical_listing?: Record<string, any> | null;
  market_context?: Record<string, any> | null;
  platform_results?: Record<string, any>[];
  optimization_suggestion?: Record<string, any> | null;
  rewrite_instruction?: string | null;
  last_error?: string | null;
  selected_platforms?: string[];
}
