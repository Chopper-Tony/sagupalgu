"""
Publish Job Repository — publish_jobs 테이블 CRUD.

Per-account lock은 DB 유니크 인덱스(idx_publish_jobs_account_lock)로 강제.
워커 점유는 locked_by + locked_at 컬럼으로 관리.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from app.domain.publish_job import (
    WORKER_LOCK_TIMEOUT_SECONDS,
    PublishJobStatus,
)

logger = logging.getLogger(__name__)

TABLE = "publish_jobs"


class PublishJobRepository:

    def _get_client(self):
        from app.db.client import get_supabase
        return get_supabase()

    # ── 생성 ──────────────────────────────────────────────────────

    def create(
        self,
        session_id: str,
        user_id: str,
        platform: str,
        payload: dict[str, Any],
        max_attempts: int = 3,
    ) -> dict[str, Any]:
        """게시 작업을 큐에 등록한다."""
        row = {
            "id": str(uuid.uuid4()),
            "session_id": session_id,
            "user_id": user_id,
            "platform": platform,
            "payload_jsonb": payload,
            "status": PublishJobStatus.PENDING.value,
            "max_attempts": max_attempts,
        }
        result = (
            self._get_client()
            .table(TABLE)
            .insert(row)
            .execute()
        )
        logger.info(
            "publish_job_created job_id=%s session=%s platform=%s",
            row["id"], session_id, platform,
        )
        return result.data[0] if result.data else row

    def create_batch(
        self,
        session_id: str,
        user_id: str,
        platforms: list[str],
        packages: dict[str, Any],
        max_attempts: int = 3,
    ) -> list[dict[str, Any]]:
        """여러 플랫폼 게시 작업을 한번에 등록한다."""
        jobs = []
        for platform in platforms:
            payload = packages.get(platform, {})
            job = self.create(
                session_id=session_id,
                user_id=user_id,
                platform=platform,
                payload=payload,
                max_attempts=max_attempts,
            )
            jobs.append(job)
        return jobs

    # ── 조회 ──────────────────────────────────────────────────────

    def get_by_id(self, job_id: str) -> dict[str, Any] | None:
        result = (
            self._get_client()
            .table(TABLE)
            .select("*")
            .eq("id", job_id)
            .execute()
        )
        return result.data[0] if result.data else None

    def get_by_session(self, session_id: str) -> list[dict[str, Any]]:
        result = (
            self._get_client()
            .table(TABLE)
            .select("*")
            .eq("session_id", session_id)
            .order("created_at")
            .execute()
        )
        return result.data or []

    def get_pending_jobs(self, limit: int = 10) -> list[dict[str, Any]]:
        """대기 중인 작업을 가져온다. retry_scheduled도 시간 도래 시 포함."""
        now = datetime.now(timezone.utc).isoformat()
        result = (
            self._get_client()
            .table(TABLE)
            .select("*")
            .in_("status", [PublishJobStatus.PENDING.value])
            .order("created_at")
            .limit(limit)
            .execute()
        )
        pending = result.data or []

        # retry 시간 도래한 작업도 포함
        retry_result = (
            self._get_client()
            .table(TABLE)
            .select("*")
            .eq("status", PublishJobStatus.RETRY_SCHEDULED.value)
            .lte("next_retry_at", now)
            .order("next_retry_at")
            .limit(limit)
            .execute()
        )
        return pending + (retry_result.data or [])

    # ── 워커 점유 (claim) ─────────────────────────────────────────

    def claim(self, job_id: str, worker_id: str) -> bool:
        """워커가 작업을 점유한다. Per-account lock은 DB 유니크 인덱스로 강제."""
        now = datetime.now(timezone.utc).isoformat()
        try:
            result = (
                self._get_client()
                .table(TABLE)
                .update({
                    "status": PublishJobStatus.CLAIMED.value,
                    "locked_by": worker_id,
                    "locked_at": now,
                })
                .eq("id", job_id)
                .in_("status", [
                    PublishJobStatus.PENDING.value,
                    PublishJobStatus.RETRY_SCHEDULED.value,
                ])
                .execute()
            )
            if result.data:
                logger.info(
                    "publish_job_claimed job_id=%s worker=%s",
                    job_id, worker_id,
                )
                return True
            return False
        except Exception as e:
            # Per-account lock 충돌 (유니크 인덱스 위반)
            logger.warning(
                "publish_job_claim_failed job_id=%s worker=%s error=%s",
                job_id, worker_id, e,
            )
            return False

    # ── 상태 업데이트 ─────────────────────────────────────────────

    def start(self, job_id: str) -> None:
        """작업 실행 시작."""
        now = datetime.now(timezone.utc).isoformat()
        self._get_client().table(TABLE).update({
            "status": PublishJobStatus.RUNNING.value,
            "started_at": now,
        }).eq("id", job_id).execute()

    def complete(
        self,
        job_id: str,
        evidence_urls: list[str] | None = None,
    ) -> None:
        """작업 성공 완료."""
        now = datetime.now(timezone.utc).isoformat()
        self._get_client().table(TABLE).update({
            "status": PublishJobStatus.COMPLETED.value,
            "finished_at": now,
            "locked_by": None,
            "locked_at": None,
            "evidence_urls_jsonb": evidence_urls or [],
        }).eq("id", job_id).execute()
        logger.info("publish_job_completed job_id=%s", job_id)

    def fail(
        self,
        job_id: str,
        error_code: str,
        error_message: str,
        auto_recoverable: bool = False,
        evidence_urls: list[str] | None = None,
    ) -> None:
        """작업 실패 처리. auto_recoverable이면 재시도 예약."""
        job = self.get_by_id(job_id)
        if not job:
            return

        now = datetime.now(timezone.utc).isoformat()
        attempt = job.get("attempt_count", 0) + 1
        max_attempts = job.get("max_attempts", 3)

        if auto_recoverable and attempt < max_attempts:
            # 재시도 예약 (지수 백오프)
            from app.domain.publish_policy import get_retry_delay
            delay = get_retry_delay(attempt)
            next_retry = datetime.now(timezone.utc).timestamp() + delay
            next_retry_iso = datetime.fromtimestamp(
                next_retry, tz=timezone.utc
            ).isoformat()

            self._get_client().table(TABLE).update({
                "status": PublishJobStatus.RETRY_SCHEDULED.value,
                "attempt_count": attempt,
                "error_code": error_code,
                "error_message": error_message,
                "next_retry_at": next_retry_iso,
                "locked_by": None,
                "locked_at": None,
                "evidence_urls_jsonb": evidence_urls or [],
            }).eq("id", job_id).execute()
            logger.info(
                "publish_job_retry_scheduled job_id=%s attempt=%d/%d delay=%.0fs",
                job_id, attempt, max_attempts, delay,
            )
        else:
            # 최종 실패
            self._get_client().table(TABLE).update({
                "status": PublishJobStatus.FAILED.value,
                "attempt_count": attempt,
                "finished_at": now,
                "error_code": error_code,
                "error_message": error_message,
                "locked_by": None,
                "locked_at": None,
                "evidence_urls_jsonb": evidence_urls or [],
            }).eq("id", job_id).execute()
            logger.warning(
                "publish_job_failed job_id=%s error_code=%s attempts=%d",
                job_id, error_code, attempt,
            )

    def cancel(self, job_id: str) -> bool:
        """작업 취소. 터미널 상태가 아닌 경우만 가능."""
        result = (
            self._get_client()
            .table(TABLE)
            .update({
                "status": PublishJobStatus.CANCELLED.value,
                "locked_by": None,
                "locked_at": None,
            })
            .eq("id", job_id)
            .not_.in_("status", [
                PublishJobStatus.COMPLETED.value,
                PublishJobStatus.FAILED.value,
                PublishJobStatus.CANCELLED.value,
            ])
            .execute()
        )
        if result.data:
            logger.info("publish_job_cancelled job_id=%s", job_id)
            return True
        return False

    # ── 운영 ──────────────────────────────────────────────────────

    def release_stuck_jobs(self) -> int:
        """lock 타임아웃 초과한 stuck 작업을 해제한다."""
        threshold = datetime.now(timezone.utc).timestamp() - WORKER_LOCK_TIMEOUT_SECONDS
        threshold_iso = datetime.fromtimestamp(
            threshold, tz=timezone.utc
        ).isoformat()

        result = (
            self._get_client()
            .table(TABLE)
            .update({
                "status": PublishJobStatus.FAILED.value,
                "error_code": "worker_stuck",
                "error_message": f"Worker lock timeout ({WORKER_LOCK_TIMEOUT_SECONDS}s)",
                "locked_by": None,
                "locked_at": None,
            })
            .in_("status", [PublishJobStatus.CLAIMED.value, PublishJobStatus.RUNNING.value])
            .lte("locked_at", threshold_iso)
            .execute()
        )
        count = len(result.data) if result.data else 0
        if count > 0:
            logger.warning("publish_jobs_stuck_released count=%d", count)
        return count

    def get_queue_stats(self) -> dict[str, int]:
        """큐 상태 통계."""
        stats: dict[str, int] = {}
        for status in PublishJobStatus:
            result = (
                self._get_client()
                .table(TABLE)
                .select("id", count="exact")
                .eq("status", status.value)
                .execute()
            )
            stats[status.value] = result.count or 0
        return stats

    def pause_platform(self, platform: str) -> int:
        """특정 플랫폼의 대기 중 작업을 일시 중지(취소)."""
        result = (
            self._get_client()
            .table(TABLE)
            .update({"status": PublishJobStatus.CANCELLED.value})
            .eq("platform", platform)
            .eq("status", PublishJobStatus.PENDING.value)
            .execute()
        )
        count = len(result.data) if result.data else 0
        logger.info("platform_paused platform=%s cancelled=%d", platform, count)
        return count

    def disable_user_publishing(self, user_id: str) -> int:
        """특정 사용자의 대기 중 작업을 모두 취소."""
        result = (
            self._get_client()
            .table(TABLE)
            .update({"status": PublishJobStatus.CANCELLED.value})
            .eq("user_id", user_id)
            .in_("status", [
                PublishJobStatus.PENDING.value,
                PublishJobStatus.RETRY_SCHEDULED.value,
            ])
            .execute()
        )
        count = len(result.data) if result.data else 0
        logger.info("user_publishing_disabled user=%s cancelled=%d", user_id, count)
        return count
