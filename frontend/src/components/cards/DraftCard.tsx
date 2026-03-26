import { useState } from "react";
import type { CanonicalListing, MarketContext } from "../../types";
import "./DraftCard.css";

interface CriticFeedback {
  type: string;
  impact: string;
  reason: string;
}

interface DraftCardProps {
  listing: CanonicalListing;
  marketContext: MarketContext | null;
  criticScore: number | null;
  criticFeedback: CriticFeedback[];
  onApprove: (platforms: string[]) => void;
  onRewrite: (instruction: string) => void;
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

export function DraftCard({ listing, marketContext, criticScore, criticFeedback, onApprove, onRewrite }: DraftCardProps) {
  const [selectedPlatforms, setSelectedPlatforms] = useState<string[]>(PLATFORMS);
  const [rewriteText, setRewriteText] = useState("");
  const [showRewrite, setShowRewrite] = useState(false);

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

      {listing.images && listing.images.length > 0 && (
        <div className="draft-card__images">
          {listing.images.map((url, i) => (
            <img
              key={i}
              src={url}
              alt={`상품 이미지 ${i + 1}`}
              className="draft-card__image"
              loading="lazy"
            />
          ))}
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
            <ul className="draft-card__feedback-list">
              {criticFeedback.map((fb, i) => (
                <li key={i} className="draft-card__feedback-item">
                  <span className="draft-card__feedback-type">{TYPE_LABEL[fb.type] ?? fb.type}</span>
                  <span className={`draft-card__feedback-impact draft-card__feedback-impact--${fb.impact}`}>
                    {IMPACT_LABEL[fb.impact] ?? fb.impact}
                  </span>
                  <span className="draft-card__feedback-reason">{fb.reason}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
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
          onClick={() => onApprove(selectedPlatforms.map((p) => PLATFORM_MAP[p] ?? p))}
          disabled={selectedPlatforms.length === 0}
        >
          게시 준비
        </button>
        <button
          className="draft-card__rewrite-btn"
          onClick={() => setShowRewrite((v) => !v)}
        >
          수정 요청
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
    </div>
  );
}
