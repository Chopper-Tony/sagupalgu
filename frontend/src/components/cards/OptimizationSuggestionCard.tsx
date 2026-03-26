import type { OptimizationSuggestion } from "../../types";
import "./OptimizationSuggestionCard.css";

interface OptimizationSuggestionCardProps {
  suggestion: OptimizationSuggestion;
  onRestart: () => void;
}

export function OptimizationSuggestionCard({ suggestion, onRestart }: OptimizationSuggestionCardProps) {
  return (
    <div className="optimization-card">
      <div className="optimization-card__header">
        <span className="optimization-card__icon">💡</span>
        <div>
          <p className="optimization-card__title">가격 최적화 제안</p>
          <p className="optimization-card__subtitle">
            게시 {suggestion.days_elapsed}일 경과 — AI가 새 가격을 제안합니다.
          </p>
        </div>
      </div>

      <div className="optimization-card__body">
        <div className="optimization-card__price-row">
          <span className="optimization-card__price-label">제안 가격</span>
          <span className="optimization-card__price-value">
            {suggestion.suggested_price.toLocaleString()}원
          </span>
        </div>
        <p className="optimization-card__reason">{suggestion.reason}</p>
        {suggestion.suggestions && suggestion.suggestions.length > 0 && (
          <ul className="optimization-card__suggestions">
            {suggestion.suggestions.map((s: string, i: number) => (
              <li key={i} className="optimization-card__suggestion-item">{s}</li>
            ))}
          </ul>
        )}
      </div>

      <div className="optimization-card__actions">
        <button className="optimization-card__restart-btn" onClick={onRestart}>
          새로 시작하기
        </button>
      </div>
    </div>
  );
}
