// ─────────────────────────────────────────────
// Session 상태 타입 (백엔드 session_status.py 와 1:1 대응)
// ─────────────────────────────────────────────

export type SessionStatus =
  | "session_created"
  | "images_uploaded"
  | "awaiting_product_confirmation"
  | "market_analyzing"
  | "product_confirmed"
  | "draft_generated"
  | "awaiting_publish_approval"
  | "publishing"
  | "completed"
  | "awaiting_sale_status_update"
  | "optimization_suggested"
  | "publishing_failed"
  | "failed";

// ─────────────────────────────────────────────
// 상품 정보
// ─────────────────────────────────────────────

export interface ProductCandidate {
  brand: string;
  model: string;
  category: string;
  confidence: number;
}

export interface ConfirmedProduct {
  brand: string;
  model: string;
  category: string;
  source: "user_input" | "vision";
}

// ─────────────────────────────────────────────
// 판매글 (canonical listing)
// ─────────────────────────────────────────────

export interface CanonicalListing {
  title: string;
  description: string;
  price: number;
  tags: string[];
  images: string[];
}

// ─────────────────────────────────────────────
// 시세 컨텍스트
// ─────────────────────────────────────────────

export interface MarketContext {
  median_price: number | null;
  price_band: [number, number] | [];
  sample_count: number;
  crawler_sources: string[];
}

// ─────────────────────────────────────────────
// 게시 결과
// ─────────────────────────────────────────────

export interface PlatformResult {
  platform: string;
  success: boolean;
  url?: string;
  error?: string;
}

// ─────────────────────────────────────────────
// 최적화 제안
// ─────────────────────────────────────────────

export interface OptimizationSuggestion {
  suggested_price: number;
  reason: string;
  days_elapsed: number;
  suggestions?: string[];
  urgency?: string;
  recommend_relist?: boolean;
}

// ─────────────────────────────────────────────
// 세션 API 응답 (GET /sessions/{id})
// ─────────────────────────────────────────────

export interface SessionResponse {
  session_id: string;
  status: SessionStatus;
  next_action: string | null;
  needs_user_input: boolean;
  clarification_prompt: string | null;
  product_candidates: ProductCandidate[];
  confirmed_product: ConfirmedProduct | null;
  canonical_listing: CanonicalListing | null;
  market_context: MarketContext | null;
  platform_results: PlatformResult[];
  optimization_suggestion: OptimizationSuggestion | null;
  rewrite_instruction: string | null;
  last_error: string | null;
  image_urls: string[];
  selected_platforms: string[];
  agent_trace?: {
    tool_calls: Array<{ tool_name: string; success: boolean }>;
    rewrite_history: unknown[];
    decision_rationale: string[];
    plan: { focus: string; steps: string[] } | null;
    critic_score: number | null;
    critic_feedback: Array<{ type: string; impact: string; reason: string }>;
    job_progress?: Record<string, {
      platform: string;
      event: string;
      timestamp?: number;
      listing_id?: string;
      listing_url?: string;
      error_code?: string;
      error_message?: string;
    }>;
  };
}
