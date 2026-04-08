import type { PlatformResult } from "../../types";
import { platformLabel } from "../../lib/sessionStatusUiMap";
import "./PublishResultCard.css";

interface PublishResultCardProps {
  results: PlatformResult[];
  sessionId?: string;
  onUpdateSaleStatus: () => void;
}

const PLATFORM_HOME: Record<string, string> = {
  bunjang: "https://m.bunjang.co.kr",
  joongna: "https://web.joongna.com",
  daangn: "https://www.daangn.com",
};

function isAccessBlocked(error: string | undefined): boolean {
  if (!error) return false;
  const msg = error.toLowerCase();
  return msg.includes("차단") || msg.includes("403") || msg.includes("cloudfront");
}

export function PublishResultCard({ results, sessionId, onUpdateSaleStatus }: PublishResultCardProps) {
  const successCount = results.filter((r) => r.success).length;
  const blockedResults = results.filter((r) => !r.success && isAccessBlocked(r.error));

  return (
    <div className="publish-result-card">
      <div className="publish-result-card__header">
        <span className="publish-result-card__icon">
          {successCount === results.length ? "✅" : "⚠️"}
        </span>
        <div>
          <p className="publish-result-card__title">
            {successCount === results.length
              ? "게시가 완료됐습니다"
              : `${successCount}/${results.length}개 플랫폼에 게시됐습니다`}
          </p>
          <p className="publish-result-card__subtitle">
            판매 현황을 주기적으로 확인해 드릴게요.
          </p>
        </div>
      </div>

      <div className="publish-result-card__results">
        {results.map((r) => (
          <div key={r.platform} className="publish-result-card__result">
            <div className="publish-result-card__result-left">
              <span className={`publish-result-card__result-dot${r.success ? " publish-result-card__result-dot--success" : " publish-result-card__result-dot--fail"}`} />
              <span className="publish-result-card__result-platform">{platformLabel(r.platform)}</span>
            </div>
            {r.success ? (
              <a
                href={r.url || PLATFORM_HOME[r.platform] || "#"}
                target="_blank"
                rel="noopener noreferrer"
                className="publish-result-card__result-link"
              >
                게시글 보기 →
              </a>
            ) : (
              <span className="publish-result-card__result-error">{r.error ?? "실패"}</span>
            )}
          </div>
        ))}
      </div>

      {blockedResults.length > 0 && (
        <div className="publish-result-card__extension-notice">
          <p style={{ fontSize: "12px", color: "#fbbf24", marginBottom: "6px" }}>
            {blockedResults.map((r) => platformLabel(r.platform)).join(", ")}는 서버에서 접속이 차단됩니다.
          </p>
          <p style={{ fontSize: "12px", color: "#93c5fd" }}>
            크롬 익스텐션을 열어 아래 세션 ID를 입력한 후 "자동 게시 시작"을 눌러주세요.
          </p>
          {sessionId && (
            <code
              style={{
                display: "block", fontSize: "11px", color: "#e0e0e0",
                background: "#1e293b", padding: "6px 8px", borderRadius: "4px",
                marginTop: "4px", cursor: "pointer", wordBreak: "break-all",
              }}
              onClick={() => navigator.clipboard.writeText(sessionId)}
              title="클릭하여 복사"
            >
              {sessionId}
            </code>
          )}
        </div>
      )}

      <button className="publish-result-card__status-btn" onClick={onUpdateSaleStatus}>
        판매 상태 업데이트
      </button>
    </div>
  );
}
