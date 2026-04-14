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

export function PublishResultCard({ results, sessionId, onUpdateSaleStatus }: PublishResultCardProps) {
  const serverResults = results.filter((r) => !isExtensionRequired(r));
  const extensionResults = results.filter((r) => isExtensionRequired(r));

  const successCount = serverResults.filter((r) => r.success).length;

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

  const handleAutoPublish = (platform: string) => {
    window.postMessage({
      type: "SAGUPALGU_PUBLISH",
      sessionId,
      platform,
      serverUrl: window.location.origin,
    }, "*");
  };

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

        {/* 익스텐션 전용 — 자동 게시 버튼을 플랫폼명 옆에 배치 */}
        {extensionResults.map((r) => (
          <div key={r.platform} className="publish-result-card__result">
            <div className="publish-result-card__result-left">
              <span className="publish-result-card__result-dot publish-result-card__result-dot--extension" />
              <span className="publish-result-card__result-platform">{platformLabel(r.platform)}</span>
            </div>
            {sessionId && (
              <button
                className="publish-result-card__inline-publish-btn"
                style={{
                  background: r.platform === "bunjang" ? "#dc2626" : "#059669",
                }}
                onClick={() => handleAutoPublish(r.platform)}
              >
                {platformLabel(r.platform)} 자동 게시
              </button>
            )}
          </div>
        ))}
      </div>

      <button className="publish-result-card__status-btn" onClick={onUpdateSaleStatus}>
        판매 상태 업데이트
      </button>
    </div>
  );
}
