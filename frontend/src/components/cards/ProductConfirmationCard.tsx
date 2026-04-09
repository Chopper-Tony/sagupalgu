import { useState } from "react";
import type { ProductCandidate, ConfirmedProduct } from "../../types";
import "./ProductConfirmationCard.css";

interface ProductConfirmationCardProps {
  candidates: ProductCandidate[];
  clarificationPrompt: string | null;
  onConfirm: (product: ConfirmedProduct) => void;
}

export function ProductConfirmationCard({
  candidates,
  clarificationPrompt,
  onConfirm,
}: ProductConfirmationCardProps) {
  const top = candidates[0] ?? null;

  const [brand, setBrand] = useState(top?.brand ?? "");
  const [model, setModel] = useState(top?.model ?? "");
  const [category, setCategory] = useState(top?.category ?? "");
  const [touched, setTouched] = useState<Record<string, boolean>>({});

  const handleConfirm = (candidate?: ProductCandidate) => {
    if (candidate) {
      onConfirm({ brand: candidate.brand, model: candidate.model, category: candidate.category, source: "vision" });
    } else {
      if (!brand.trim() || !model.trim()) return;
      onConfirm({ brand: brand.trim(), model: model.trim(), category: category.trim(), source: "user_input" });
    }
  };

  return (
    <div className="product-confirm-card">
      <div className="product-confirm-card__header">
        <span className="product-confirm-card__icon">🔍</span>
        <div>
          <p className="product-confirm-card__title">상품을 확인해 주세요</p>
          <p className="product-confirm-card__subtitle">
            {clarificationPrompt ?? "AI가 분석한 상품 정보가 맞는지 확인하거나 직접 수정해 주세요."}
          </p>
        </div>
      </div>

      {/* 후보 없음 안내 */}
      {candidates.length === 0 && (
        <p className="product-confirm-card__no-candidates">
          AI가 감지한 상품이 없습니다. 직접 입력해주세요.
        </p>
      )}

      {/* 후보 카드 */}
      {candidates.length > 0 && (
        <div className="product-confirm-card__candidates">
          {candidates.slice(0, 3).map((c, i) => (
            <button
              key={i}
              className="product-confirm-card__candidate"
              onClick={() => handleConfirm(c)}
            >
              <div className="product-confirm-card__candidate-info">
                <span className="product-confirm-card__candidate-name">
                  {c.brand} {c.model}
                </span>
                <span className="product-confirm-card__candidate-category">{c.category}</span>
              </div>
              <div className="product-confirm-card__confidence">
                <div
                  className="product-confirm-card__confidence-bar"
                  style={{ width: `${Math.round(c.confidence * 100)}%` }}
                />
                <span className="product-confirm-card__confidence-label">
                  {Math.round(c.confidence * 100)}%
                </span>
              </div>
            </button>
          ))}
        </div>
      )}

      {/* 직접 입력 */}
      <div className="product-confirm-card__manual">
        <p className="product-confirm-card__manual-label">직접 입력</p>
        <div className="product-confirm-card__fields">
          <div className="product-confirm-card__field-wrap">
            <input
              className={`product-confirm-card__input${touched.brand && !brand.trim() ? " product-confirm-card__input--error" : ""}`}
              placeholder="브랜드 (예: 애플, 삼성, LG)"
              value={brand}
              onChange={(e) => setBrand(e.target.value)}
              onBlur={() => setTouched((prev) => ({ ...prev, brand: true }))}
            />
            {touched.brand && !brand.trim() && (
              <span className="product-confirm-card__hint">필수 입력</span>
            )}
          </div>
          <div className="product-confirm-card__field-wrap">
            <input
              className={`product-confirm-card__input${touched.model && !model.trim() ? " product-confirm-card__input--error" : ""}`}
              placeholder="모델명 (예: 아이폰 15 프로, 갤럭시 S24)"
              value={model}
              onChange={(e) => setModel(e.target.value)}
              onBlur={() => setTouched((prev) => ({ ...prev, model: true }))}
            />
            {touched.model && !model.trim() && (
              <span className="product-confirm-card__hint">필수 입력</span>
            )}
          </div>
          <div className="product-confirm-card__field-wrap">
            <input
              className={`product-confirm-card__input${touched.category && !category.trim() ? " product-confirm-card__input--error" : ""}`}
              placeholder="카테고리 (예: 스마트폰, 노트북, 태블릿)"
              value={category}
              onChange={(e) => setCategory(e.target.value)}
              onBlur={() => setTouched((prev) => ({ ...prev, category: true }))}
            />
            {touched.category && !category.trim() && (
              <span className="product-confirm-card__hint">필수 입력</span>
            )}
          </div>
        </div>
        <button
          className="product-confirm-card__submit"
          onClick={() => handleConfirm()}
          disabled={!brand.trim() || !model.trim()}
        >
          이 정보로 진행
        </button>
      </div>
    </div>
  );
}
