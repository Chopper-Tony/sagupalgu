import type { SessionStatus } from "../../types";
import "./ErrorCard.css";

interface ErrorCardProps {
  code: string;
  message: string;
  currentStatus: SessionStatus | null;
  onAction?: (action: string, payload?: unknown) => void;
}

interface RecoveryAction {
  label: string;
  action: string;
}

const RECOVERY_ACTIONS: Partial<Record<string, RecoveryAction[]>> = {
  publishing_failed: [
    { label: "다시 시도", action: "retry_publish" },
    { label: "플랫폼 변경 후 재시도", action: "change_platform" },
    { label: "판매글 수정", action: "edit_draft" },
  ],
  failed: [
    { label: "처음부터 다시 시작", action: "restart" },
  ],
};

export function ErrorCard({ code, message, currentStatus, onAction }: ErrorCardProps) {
  const actions = RECOVERY_ACTIONS[currentStatus ?? ""] ?? [
    { label: "처음부터 다시 시작", action: "restart" },
  ];

  return (
    <div className="error-card">
      <div className="error-card__header">
        <span className="error-card__icon">⚠️</span>
        <span className="error-card__title">오류가 발생했습니다</span>
      </div>
      <p className="error-card__message">{message}</p>
      {code && (
        <details className="error-card__details">
          <summary className="error-card__details-summary">오류 상세 보기</summary>
          <p className="error-card__code">오류 코드: {code}</p>
        </details>
      )}
      <div className="error-card__actions">
        {actions.map((a) => (
          <button
            key={a.action}
            className="error-card__action-btn"
            onClick={() => onAction?.(a.action)}
          >
            {a.label}
          </button>
        ))}
      </div>
    </div>
  );
}
