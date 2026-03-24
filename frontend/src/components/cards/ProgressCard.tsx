import type { SessionStatus } from "../../types";
import { PROGRESS_COPY } from "../../lib/sessionStatusUiMap";
import "./ProgressCard.css";

interface ProgressCardProps {
  status: SessionStatus;
  message?: string;
}

export function ProgressCard({ status, message }: ProgressCardProps) {
  const copy = PROGRESS_COPY[status];
  const title = copy?.title ?? "처리 중입니다";
  const subtitle = message ?? copy?.subtitle ?? "잠시만 기다려 주세요";

  return (
    <div className="progress-card">
      <div className="progress-card__spinner" />
      <div className="progress-card__text">
        <p className="progress-card__title">{title}</p>
        <p className="progress-card__subtitle">{subtitle}</p>
      </div>
    </div>
  );
}
