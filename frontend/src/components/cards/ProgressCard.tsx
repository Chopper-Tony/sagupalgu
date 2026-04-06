import type { SessionStatus } from "../../types";
import { PROGRESS_COPY, platformLabel } from "../../lib/sessionStatusUiMap";
import "./ProgressCard.css";

interface JobProgress {
  platform: string;
  event: string;
  timestamp?: number;
  listing_id?: string;
  listing_url?: string;
  error_code?: string;
  error_message?: string;
}

interface ProgressCardProps {
  status: SessionStatus;
  message?: string;
  jobProgress?: Record<string, JobProgress>;
}

function JobStatusBadge({ event }: { event: string }) {
  const map: Record<string, { label: string; className: string }> = {
    job_started: { label: "게시 중...", className: "progress-card__badge--running" },
    job_completed: { label: "완료", className: "progress-card__badge--success" },
    job_failed: { label: "실패", className: "progress-card__badge--failed" },
  };
  const info = map[event] ?? { label: event, className: "" };
  return <span className={`progress-card__badge ${info.className}`}>{info.label}</span>;
}

export function ProgressCard({ status, message, jobProgress }: ProgressCardProps) {
  const copy = PROGRESS_COPY[status];
  const title = copy?.title ?? "처리 중입니다";
  const subtitle = message ?? copy?.subtitle ?? "잠시만 기다려 주세요";

  const jobs = jobProgress ? Object.values(jobProgress) : [];

  return (
    <div className="progress-card">
      <div className="progress-card__spinner" />
      <div className="progress-card__text">
        <p className="progress-card__title">{title}</p>
        <p className="progress-card__subtitle">{subtitle}</p>
      </div>
      {status === "publishing" && jobs.length > 0 && (
        <div className="progress-card__jobs">
          {jobs.map((job, i) => (
            <div key={i} className="progress-card__job">
              <span className="progress-card__platform">{platformLabel(job.platform)}</span>
              <JobStatusBadge event={job.event} />
              {job.error_message && (
                <span className="progress-card__error">{job.error_message}</span>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
