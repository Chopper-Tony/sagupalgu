import "./SaleStatusCard.css";

interface SaleStatusCardProps {
  onMarkSold: () => void;
  onMarkUnsold: () => void;
}

export function SaleStatusCard({ onMarkSold, onMarkUnsold }: SaleStatusCardProps) {
  return (
    <div className="sale-status-card">
      <div className="sale-status-card__header">
        <span className="sale-status-card__icon">📦</span>
        <div>
          <p className="sale-status-card__title">판매 결과를 알려주세요</p>
          <p className="sale-status-card__subtitle">
            판매 결과에 따라 최적 가격을 제안해 드립니다.
          </p>
        </div>
      </div>

      <div className="sale-status-card__actions">
        <button className="sale-status-card__sold-btn" onClick={onMarkSold}>
          팔렸어요
        </button>
        <button className="sale-status-card__unsold-btn" onClick={onMarkUnsold}>
          아직 안 팔렸어요
        </button>
      </div>
    </div>
  );
}
