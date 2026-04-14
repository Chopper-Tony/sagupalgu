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

function isExtensionRequired(r: PlatformResult): boolean {
  return r.source === "extension_required";
}

function isAccessBlocked(error: string | undefined): boolean {
  if (!error) return false;
  const msg = error.toLowerCase();
  return msg.includes("차단") || msg.includes("403") || msg.includes("cloudfront");
}

export function PublishResultCard({ results, sessionId, onUpdateSaleStatus }: PublishResultCardProps) {
  // extension_required는 실패로 카운트하지 않음
  const serverResults = results.filter((r) => !isExtensionRequired(r));
  const extensionResults = results.filter((r) => isExtensionRequired(r));

  const successCount = serverResults.filter((r) => r.success).length;
  const blockedResults = serverResults.filter((r) => !r.success && isAccessBlocked(r.error));
  const extensionPlatforms = [
    ...extensionResults.map((r) => r.platform),
    ...blockedResults.map((r) => r.platform),
  ].filter((v, i, a) => a.indexOf(v) === i);

  // 헤더 메시지 결정
  const allServerSuccess = serverResults.length > 0 && successCount === serverResults.length;
  const noServerPlatforms = serverResults.length === 0;

  let headerIcon: string;
  let headerTitle: string;

  if (noServerPlatforms && extensionResults.length > 0) {
    headerIcon = "📎";
    headerTitle = "크롬 익스텐션에서 게시해주세요";
  } else if (allServerSuccess && extensionResults.length === 0) {
    headerIcon = "✅";
    headerTitle = "게시가 완료됐습니다";
  } else if (allServerSuccess && extensionResults.length > 0) {
    headerIcon = "✅";
    headerTitle = `서버 게시 완료 (${extensionResults.length}개는 익스텐션 필요)`;
  } else {
    headerIcon = "⚠️";
    headerTitle = `${successCount}/${serverResults.length}개 플랫폼에 게시됐습니다`;
  }

  return (
    <div className="publish-result-card">
      <div className="publish-result-card__header">
        <span className="publish-result-card__icon">{headerIcon}</span>
        <div>
          <p className="publish-result-card__title">{headerTitle}</p>
          <p className="publish-result-card__subtitle">
            판매 현황을 주기적으로 확인해 드릴게요.
          </p>
        </div>
      </div>

      <div className="publish-result-card__results">
        {/* 서버 게시 결과 */}
        {serverResults.map((r) => (
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

        {/* 익스텐션 전용 플랫폼 */}
        {extensionResults.map((r) => (
          <div key={r.platform} className="publish-result-card__result">
            <div className="publish-result-card__result-left">
              <span className="publish-result-card__result-dot publish-result-card__result-dot--extension" />
              <span className="publish-result-card__result-platform">{platformLabel(r.platform)}</span>
            </div>
            <span style={{ fontSize: "12px", color: "#93c5fd" }}>익스텐션에서 게시 가능</span>
          </div>
        ))}
      </div>

      {/* 익스텐션 자동 게시 버튼 */}
      {extensionPlatforms.length > 0 && sessionId && (
        <div className="publish-result-card__extension-notice">
          <div style={{ display: "flex", gap: "8px", flexWrap: "wrap" }}>
            {extensionPlatforms.map((platform) => (
              <button
                key={platform}
                className="publish-result-card__auto-publish-btn"
                style={{
                  flex: 1, padding: "10px", border: "none", borderRadius: "6px",
                  background: platform === "bunjang" ? "#dc2626" : "#059669",
                  color: "#fff", fontSize: "13px", fontWeight: 600, cursor: "pointer",
                  minWidth: "120px",
                }}
                onClick={() => {
                  window.postMessage({
                    type: "SAGUPALGU_PUBLISH",
                    sessionId,
                    platform,
                    serverUrl: window.location.origin,
                  }, "*");
                }}
              >
                {platformLabel(platform)} 자동 게시
              </button>
            ))}
          </div>
          <details style={{ marginTop: "8px" }}>
            <summary style={{ fontSize: "11px", color: "#94a3b8", cursor: "pointer" }}>
              수동 게시 (세션 ID 복사)
            </summary>
            {sessionId && (
              <code
                style={{
                  display: "block", fontSize: "11px", color: "var(--text-secondary)",
                  background: "var(--bg-tertiary)", padding: "6px 8px", borderRadius: "4px",
                  marginTop: "4px", cursor: "pointer", wordBreak: "break-all",
                }}
                onClick={() => {
                  if (navigator.clipboard?.writeText) {
                    navigator.clipboard.writeText(sessionId).catch(() => {});
                  }
                }}
                title="클릭하여 복사"
              >
                {sessionId}
              </code>
            )}
          </details>
        </div>
      )}

      <button className="publish-result-card__status-btn" onClick={onUpdateSaleStatus}>
        판매 상태 업데이트
      </button>
    </div>
  );
}
