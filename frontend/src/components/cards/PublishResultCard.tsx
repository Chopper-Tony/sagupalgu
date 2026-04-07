import type { PlatformResult } from "../../types";
import { platformLabel } from "../../lib/sessionStatusUiMap";
import "./PublishResultCard.css";

interface PublishResultCardProps {
  results: PlatformResult[];
  onUpdateSaleStatus: () => void;
}

const PLATFORM_HOME: Record<string, string> = {
  bunjang: "https://m.bunjang.co.kr",
  joongna: "https://web.joongna.com",
  daangn: "https://www.daangn.com",
};

export function PublishResultCard({ results, onUpdateSaleStatus }: PublishResultCardProps) {
  const successCount = results.filter((r) => r.success).length;

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

      <button className="publish-result-card__status-btn" onClick={onUpdateSaleStatus}>
        판매 상태 업데이트
      </button>
    </div>
  );
}
