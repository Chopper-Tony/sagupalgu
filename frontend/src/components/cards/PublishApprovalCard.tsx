import type { CanonicalListing } from "../../types";
import { platformLabel } from "../../lib/sessionStatusUiMap";
import "./PublishApprovalCard.css";

interface PublishApprovalCardProps {
  listing: CanonicalListing;
  platforms: string[];
  onPublish: () => void;
  onEdit: () => void;
}

export function PublishApprovalCard({ listing, platforms, onPublish, onEdit }: PublishApprovalCardProps) {
  return (
    <div className="publish-approval-card">
      <div className="publish-approval-card__header">
        <span className="publish-approval-card__icon">🚀</span>
        <div>
          <p className="publish-approval-card__title">게시 준비 완료</p>
          <p className="publish-approval-card__subtitle">
            아래 플랫폼에 판매글을 게시합니다.
          </p>
        </div>
      </div>

      <div className="publish-approval-card__summary">
        <p className="publish-approval-card__listing-title">{listing.title}</p>
        <p className="publish-approval-card__price">{listing.price.toLocaleString()}원</p>
      </div>

      <div className="publish-approval-card__platforms">
        {platforms.map((p) => (
          <span key={p} className="publish-approval-card__platform">{platformLabel(p)}</span>
        ))}
      </div>

      <div className="publish-approval-card__actions">
        <button className="publish-approval-card__publish-btn" onClick={onPublish}>
          지금 게시하기
        </button>
        <button className="publish-approval-card__edit-btn" onClick={onEdit}>
          판매글 수정
        </button>
      </div>
    </div>
  );
}
