import { useState } from "react";
import type { CanonicalListing, MarketContext } from "../../types";
import "./DraftCard.css";

interface CriticFeedback {
  type: string;
  impact: string;
  reason: string;
}

interface ToolCall {
  tool_name: string;
  success: boolean;
}

interface AgentPlan {
  focus: string;
  steps: string[];
}

interface DraftCardProps {
  listing: CanonicalListing;
  marketContext: MarketContext | null;
  criticScore: number | null;
  criticFeedback: CriticFeedback[];
  toolCalls: ToolCall[];
  decisionRationale: string[];
  plan: AgentPlan | null;
  onApprove: (platforms: string[]) => void;
  onRewrite: (instruction: string) => void;
  onDirectEdit: (listing: CanonicalListing) => void;
}

const PLATFORM_MAP: Record<string, string> = {
  "번개장터": "bunjang",
  "중고나라": "joongna",
  "당근마켓": "daangn",
};
const PLATFORMS = Object.keys(PLATFORM_MAP);

const IMPACT_LABEL: Record<string, string> = { high: "높음", medium: "보통", low: "낮음" };
const TYPE_LABEL: Record<string, string> = {
  title: "제목", description: "설명", price: "가격", trust: "신뢰도", seo: "검색 최적화", missing: "누락",
};

const TOOL_LABEL: Record<string, string> = {
  lc_market_crawl_tool: "시세 크롤링",
  lc_rag_price_tool: "RAG 가격 검색",
  lc_generate_listing_tool: "판매글 생성",
  lc_rewrite_listing_tool: "판매글 재작성",
  lc_diagnose_publish_failure_tool: "게시 실패 진단",
  lc_auto_patch_tool: "자동 패치",
  lc_discord_alert_tool: "Discord 알림",
};

export function DraftCard({ listing, marketContext, criticScore, criticFeedback, toolCalls, decisionRationale, plan, onApprove, onRewrite, onDirectEdit }: DraftCardProps) {
  const [selectedPlatforms, setSelectedPlatforms] = useState<string[]>([]);
  const [rewriteText, setRewriteText] = useState("");
  const [showRewrite, setShowRewrite] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [showDirectEdit, setShowDirectEdit] = useState(false);
  const [editTitle, setEditTitle] = useState(listing.title || "");
  const [editDescription, setEditDescription] = useState(listing.description || "");
  const [editPrice, setEditPrice] = useState(String(listing.price ?? 0));

  const togglePlatform = (p: string) => {
    setSelectedPlatforms((prev) =>
      prev.includes(p) ? prev.filter((x) => x !== p) : [...prev, p]
    );
  };

  const handleRewrite = () => {
    if (!rewriteText.trim()) return;
    onRewrite(rewriteText.trim());
    setRewriteText("");
    setShowRewrite(false);
  };

  const handleDirectEdit = () => {
    const price = parseInt(editPrice, 10);
    if (!editTitle.trim() || isNaN(price)) return;
    onDirectEdit({
      ...listing,
      title: editTitle.trim(),
      description: editDescription.trim(),
      price,
    });
    setShowDirectEdit(false);
  };

  return (
    <div className="draft-card">
      <div className="draft-card__header">
        <span className="draft-card__icon">📝</span>
        <p className="draft-card__title">판매글 초안이 완성됐습니다</p>
      </div>

      {marketContext?.median_price && (
        <div className="draft-card__market">
          <span className="draft-card__market-label">시세</span>
          <span className="draft-card__market-price">
            {marketContext.median_price.toLocaleString()}원
          </span>
          {marketContext.price_band.length === 2 && (
            <span className="draft-card__market-band">
              ({marketContext.price_band[0].toLocaleString()} ~{" "}
              {marketContext.price_band[1].toLocaleString()}원)
            </span>
          )}
        </div>
      )}

      <div className="draft-card__content">
        <p className="draft-card__listing-title">{listing.title || "제목 없음"}</p>
        <p className="draft-card__price">{(listing.price ?? 0).toLocaleString()}원</p>
        <p className="draft-card__description">{listing.description || ""}</p>
        {(listing.tags ?? []).length > 0 && (
          <div className="draft-card__tags">
            {(listing.tags ?? []).map((t) => (
              <span key={t} className="draft-card__tag">#{t}</span>
            ))}
          </div>
        )}
      </div>

      {criticScore != null && (
        <div className="draft-card__feedback">
          <p className="draft-card__feedback-title">
            AI 품질 평가: <strong>{criticScore}점</strong>
          </p>
          {criticFeedback.length > 0 && (
            <table className="draft-card__feedback-table">
              <thead>
                <tr>
                  <th>항목</th>
                  <th>영향도</th>
                  <th>평가</th>
                </tr>
              </thead>
              <tbody>
                {criticFeedback.map((fb, i) => (
                  <tr key={i}>
                    <td className="draft-card__feedback-type">{TYPE_LABEL[fb.type] ?? fb.type}</td>
                    <td>
                      <span className={`draft-card__feedback-impact draft-card__feedback-impact--${fb.impact}`}>
                        {IMPACT_LABEL[fb.impact] ?? fb.impact}
                      </span>
                    </td>
                    <td className="draft-card__feedback-reason">{fb.reason}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {(toolCalls.length > 0 || decisionRationale.length > 0 || plan) && (
        <details className="draft-card__agent-trace">
          <summary className="draft-card__agent-trace-title">
            AI 의사결정 과정 ({toolCalls.length}개 도구 호출)
          </summary>

          {plan && (
            <div className="draft-card__agent-section">
              <p className="draft-card__agent-section-label">실행 전략</p>
              <p className="draft-card__agent-plan-focus">{plan.focus}</p>
              {plan.steps?.length > 0 && (
                <ol className="draft-card__agent-plan-steps">
                  {plan.steps.map((step, i) => <li key={i}>{step}</li>)}
                </ol>
              )}
            </div>
          )}

          {toolCalls.length > 0 && (
            <div className="draft-card__agent-section">
              <p className="draft-card__agent-section-label">도구 호출 이력</p>
              <div className="draft-card__agent-tools">
                {toolCalls.map((tc, i) => (
                  <span key={i} className={`draft-card__agent-tool ${tc.success ? "draft-card__agent-tool--ok" : "draft-card__agent-tool--fail"}`}>
                    {tc.success ? "✓" : "✗"} {TOOL_LABEL[tc.tool_name] ?? tc.tool_name}
                  </span>
                ))}
              </div>
            </div>
          )}

          {decisionRationale.length > 0 && (
            <div className="draft-card__agent-section">
              <p className="draft-card__agent-section-label">의사결정 근거</p>
              <ul className="draft-card__agent-rationale">
                {decisionRationale.map((r, i) => <li key={i}>{r}</li>)}
              </ul>
            </div>
          )}
        </details>
      )}

      <div className="draft-card__platforms">
        <p className="draft-card__platforms-label">게시 플랫폼 선택</p>
        <div className="draft-card__platform-list">
          {PLATFORMS.map((p) => (
            <button
              key={p}
              className={`draft-card__platform-btn${selectedPlatforms.includes(p) ? " draft-card__platform-btn--selected" : ""}`}
              onClick={() => togglePlatform(p)}
            >
              {p}
            </button>
          ))}
        </div>
      </div>

      <div className="draft-card__actions">
        <button
          className="draft-card__approve-btn"
          onClick={() => {
            setIsSubmitting(true);
            onApprove(selectedPlatforms.map((p) => PLATFORM_MAP[p] ?? p));
          }}
          disabled={selectedPlatforms.length === 0 || isSubmitting}
          style={selectedPlatforms.length === 0 ? { opacity: 0.4 } : undefined}
        >
          {isSubmitting ? "처리 중..." : "게시 준비"}
        </button>
        <button
          className="draft-card__rewrite-btn"
          onClick={() => { setShowRewrite((v) => !v); setShowDirectEdit(false); }}
        >
          수정 요청
        </button>
        <button
          className="draft-card__rewrite-btn"
          onClick={() => { setShowDirectEdit((v) => !v); setShowRewrite(false); }}
        >
          직접 수정
        </button>
      </div>

      {showRewrite && (
        <div className="draft-card__rewrite">
          <textarea
            className="draft-card__rewrite-input"
            placeholder="수정 지시사항을 입력하세요 (예: 더 신뢰감 있게 작성해주세요)"
            value={rewriteText}
            onChange={(e) => setRewriteText(e.target.value)}
            rows={3}
          />
          <button
            className="draft-card__rewrite-submit"
            onClick={handleRewrite}
            disabled={!rewriteText.trim()}
          >
            재작성
          </button>
        </div>
      )}

      {showDirectEdit && (
        <div className="draft-card__rewrite">
          <label className="draft-card__edit-label">제목</label>
          <input
            className="draft-card__rewrite-input"
            value={editTitle}
            onChange={(e) => setEditTitle(e.target.value)}
          />
          <label className="draft-card__edit-label">설명</label>
          <textarea
            className="draft-card__rewrite-input"
            value={editDescription}
            onChange={(e) => setEditDescription(e.target.value)}
            rows={5}
          />
          <label className="draft-card__edit-label">가격 (원)</label>
          <input
            className="draft-card__rewrite-input"
            type="number"
            value={editPrice}
            onChange={(e) => setEditPrice(e.target.value)}
          />
          <button
            className="draft-card__rewrite-submit"
            onClick={handleDirectEdit}
            disabled={!editTitle.trim()}
          >
            수정 완료
          </button>
        </div>
      )}
    </div>
  );
}
