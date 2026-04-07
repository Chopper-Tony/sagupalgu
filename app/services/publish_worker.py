"""
Publish Worker — Job Queue에서 작업을 폴링하고 실행하는 백그라운드 워커.

규칙:
- job당 browser context 분리
- 실패해도 cleanup 보장 (try/finally)
- 단계별 structured logging
- Per-account lock은 DB 유니크 인덱스로 강제
"""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Any

from app.db.publish_job_repository import PublishJobRepository
from app.domain.publish_job import (
    STEP_TIMEOUTS,
    WORKER_POLL_INTERVAL_SECONDS,
    PublishJobStatus,
)
from app.domain.publish_policy import (
    MAX_CONCURRENT_BROWSERS,
    classify_error,
)

logger = logging.getLogger(__name__)


class PublishWorker:
    """게시 작업 폴링 + 실행 워커."""

    def __init__(
        self,
        job_repo: PublishJobRepository,
        worker_id: str | None = None,
    ):
        self.job_repo = job_repo
        self.worker_id = worker_id or f"worker-{uuid.uuid4().hex[:8]}"
        self._running = False
        self._semaphore = asyncio.Semaphore(MAX_CONCURRENT_BROWSERS)
        self._active_tasks: set[asyncio.Task] = set()
        self._active_jobs: int = 0
        self._total_processed: int = 0
        self._total_failed: int = 0
        self._last_poll_at: str | None = None

    async def start(self) -> None:
        """워커 메인 루프. shutdown 신호까지 반복."""
        self._running = True
        logger.info("publish_worker_started worker_id=%s", self.worker_id)

        while self._running:
            try:
                # stuck 작업 해제
                self.job_repo.release_stuck_jobs()

                # 대기 작업 폴링
                jobs = self.job_repo.get_pending_jobs(limit=5)
                for job in jobs:
                    if not self._running:
                        break
                    # 동시 실행 수 체크 (active task 기준)
                    if len(self._active_tasks) < MAX_CONCURRENT_BROWSERS:
                        task = asyncio.create_task(self._process_job(job))
                        self._active_tasks.add(task)
                        task.add_done_callback(self._active_tasks.discard)

            except Exception as e:
                logger.error(
                    "publish_worker_poll_error worker=%s error=%s",
                    self.worker_id, e, exc_info=True,
                )

            await asyncio.sleep(WORKER_POLL_INTERVAL_SECONDS)

        logger.info("publish_worker_stopped worker_id=%s", self.worker_id)

    def status(self) -> dict[str, Any]:
        """워커 상태 조회. /health/ready에서 사용."""
        return {
            "alive": self._running,
            "worker_id": self.worker_id,
            "last_poll_at": self._last_poll_at,
            "active_jobs": self._active_jobs,
            "active_tasks": len(self._active_tasks),
            "total_processed": self._total_processed,
            "total_failed": self._total_failed,
        }

    async def stop(self) -> None:
        """워커 graceful shutdown — in-flight 작업 완료 대기."""
        self._running = False
        if self._active_tasks:
            logger.info(
                "publish_worker_draining active_tasks=%d", len(self._active_tasks),
            )
            await asyncio.gather(*self._active_tasks, return_exceptions=True)

    async def _process_job(self, job: dict[str, Any]) -> None:
        """단일 작업 처리. 최외곽 try/except로 워커 전체 죽지 않도록 보호."""
        try:
            await self._process_job_inner(job)
        except Exception as e:
            logger.error(
                "publish_job_unhandled_crash job_id=%s error=%s",
                job.get("id"), e, exc_info=True,
            )

    async def _process_job_inner(self, job: dict[str, Any]) -> None:
        """단일 작업 실제 처리. 세마포어 + try/finally cleanup."""
        job_id = job["id"]
        session_id = job["session_id"]
        platform = job["platform"]
        user_id = job["user_id"]

        # claim (per-account lock은 DB 유니크 인덱스로 강제)
        if not self.job_repo.claim(job_id, self.worker_id):
            return

        log_ctx = {
            "publish_job_id": job_id,
            "session_id": session_id,
            "platform": platform,
            "user_id": user_id,
            "worker_id": self.worker_id,
            "attempt_count": job.get("attempt_count", 0) + 1,
        }

        async with self._semaphore:
            # 실행 전 세션 상태 검증 — publishing이 아니면 스킵
            try:
                from app.db.client import get_supabase
                sess = get_supabase().table("sell_sessions").select(
                    "status"
                ).eq("id", session_id).execute()
                if sess.data and sess.data[0].get("status") != "publishing":
                    logger.info(
                        "publish_job_skipped_stale session=%s status=%s job_id=%s",
                        session_id, sess.data[0].get("status"), job_id,
                    )
                    self.job_repo.cancel(job_id)
                    return
            except Exception as e:
                logger.warning("session_state_check_failed job_id=%s: %s", job_id, e)

            self.job_repo.start(job_id)
            logger.info("publish_job_started %s", log_ctx)

            start_time = time.monotonic()
            evidence_urls: list[str] = []

            try:
                result = await asyncio.wait_for(
                    self._execute_publish(job, log_ctx),
                    timeout=STEP_TIMEOUTS["total"],
                )

                duration_ms = int((time.monotonic() - start_time) * 1000)
                log_ctx["duration_ms"] = duration_ms

                if result.get("success"):
                    evidence_urls = result.get("evidence_urls", [])
                    self.job_repo.complete(job_id, evidence_urls=evidence_urls)
                    logger.info("publish_job_success %s", log_ctx)

                    # 세션 상태 업데이트
                    await self._update_session_on_complete(job, result)
                else:
                    error_code = result.get("error_code", "publish_exception")
                    error_message = result.get("error_message", "Unknown error")
                    classification = classify_error(error_code, error_message)

                    self.job_repo.fail(
                        job_id,
                        error_code=classification["error_code"],
                        error_message=error_message,
                        auto_recoverable=classification["auto_recoverable"],
                        evidence_urls=result.get("evidence_urls", []),
                    )
                    log_ctx["error_code"] = error_code
                    logger.warning("publish_job_failed_result %s", log_ctx)

                    await self._update_session_on_failure(job, result)

            except asyncio.TimeoutError:
                duration_ms = int((time.monotonic() - start_time) * 1000)
                log_ctx["duration_ms"] = duration_ms
                self.job_repo.fail(
                    job_id,
                    error_code="timeout",
                    error_message=f"게시 {STEP_TIMEOUTS['total']}초 타임아웃 초과",
                    auto_recoverable=True,
                )
                logger.warning("publish_job_timeout %s", log_ctx)

            except Exception as e:
                duration_ms = int((time.monotonic() - start_time) * 1000)
                log_ctx["duration_ms"] = duration_ms
                classification = classify_error("publish_exception", str(e))
                self.job_repo.fail(
                    job_id,
                    error_code=classification["error_code"],
                    error_message=str(e),
                    auto_recoverable=classification["auto_recoverable"],
                )
                logger.error(
                    "publish_job_exception %s error=%s",
                    log_ctx, e, exc_info=True,
                )

    async def _execute_publish(
        self,
        job: dict[str, Any],
        log_ctx: dict[str, Any],
    ) -> dict[str, Any]:
        """플랫폼별 게시 실행. PublishService에 위임."""
        from app.services.publish_service import PublishService

        svc = PublishService()
        platform = job["platform"]
        payload = job.get("payload_jsonb", {})

        # 단계별 로깅
        step_start = time.monotonic()

        def _log_step(step_name: str) -> None:
            nonlocal step_start
            elapsed = int((time.monotonic() - step_start) * 1000)
            logger.info(
                "publish_step step_name=%s duration_ms=%d %s",
                step_name, elapsed, {k: log_ctx[k] for k in ("publish_job_id", "platform")},
            )
            step_start = time.monotonic()

        _log_step("job_setup")

        result = await svc.publish(platform=platform, payload=payload)

        _log_step("publish_complete")

        return {
            "success": result.success,
            "error_code": result.error_code or "",
            "error_message": result.error_message or "",
            "external_listing_id": result.external_listing_id,
            "external_url": result.external_url,
            "evidence_urls": [result.evidence_path] if result.evidence_path else [],
        }

    async def _update_session_on_complete(
        self,
        job: dict[str, Any],
        result: dict[str, Any],
    ) -> None:
        """게시 성공 시 세션 상태 업데이트. 매 job 완료마다 결과를 누적 저장."""
        session_id = job["session_id"]
        platform = job["platform"]

        try:
            from app.db.client import get_supabase

            # 현재 workflow_meta 가져오기
            existing = get_supabase().table("sell_sessions").select(
                "workflow_meta_jsonb"
            ).eq("id", session_id).execute()
            meta = {}
            if existing.data:
                meta = dict(existing.data[0].get("workflow_meta_jsonb") or {})

            # 기존 결과에 현재 플랫폼 결과 병합 (먼저 완료된 플랫폼 결과 보존)
            publish_results = dict(meta.get("publish_results") or {})
            publish_results[platform] = {
                "success": True,
                "external_listing_id": result.get("external_listing_id"),
                "external_url": result.get("external_url"),
            }
            meta["publish_results"] = publish_results

            # 모든 job 완료 여부 확인
            all_jobs = self.job_repo.get_by_session(session_id)
            all_done = all(
                j["status"] in ("completed", "failed", "cancelled")
                or j["id"] == job["id"]
                for j in all_jobs
            )

            if all_done:
                any_failure = any(
                    j["status"] == "failed" for j in all_jobs if j["id"] != job["id"]
                )
                # 실패한 job도 반영
                for j in all_jobs:
                    p = j["platform"]
                    if p not in publish_results and j["status"] == "failed":
                        publish_results[p] = {
                            "success": False,
                            "error_code": j.get("error_code"),
                        }
                meta["publish_results"] = publish_results
                meta["publish_complete"] = {
                    "results": publish_results,
                    "any_failure": any_failure,
                }
                new_status = "publishing_failed" if any_failure else "completed"

                get_supabase().table("sell_sessions").update({
                    "status": new_status,
                    "workflow_meta_jsonb": meta,
                }).eq("id", session_id).execute()

                logger.info(
                    "session_publish_complete session=%s status=%s",
                    session_id, new_status,
                )
            else:
                # 아직 다른 플랫폼 진행 중 → 결과만 저장 (상태는 유지)
                get_supabase().table("sell_sessions").update({
                    "workflow_meta_jsonb": meta,
                }).eq("id", session_id).execute()

                logger.info(
                    "session_publish_partial session=%s platform=%s",
                    session_id, platform,
                )
        except Exception as e:
            logger.error(
                "session_update_failed session=%s error=%s",
                session_id, e, exc_info=True,
            )

    async def _update_session_on_failure(
        self,
        job: dict[str, Any],
        result: dict[str, Any],
    ) -> None:
        """게시 실패 시 세션 상태 업데이트. 재시도 예약이면 대기."""
        # 재시도 예약된 경우 세션 상태는 아직 변경하지 않음
        updated_job = self.job_repo.get_by_id(job["id"])
        if updated_job and updated_job["status"] == PublishJobStatus.RETRY_SCHEDULED:
            return

        # 최종 실패 → 해당 세션의 모든 job 확인
        session_id = job["session_id"]
        all_jobs = self.job_repo.get_by_session(session_id)

        # 아직 진행 중인 작업이 있으면 대기
        still_running = any(
            j["status"] in ("pending", "claimed", "running", "retry_scheduled")
            and j["id"] != job["id"]
            for j in all_jobs
        )
        if still_running:
            return

        # 모든 작업 종료 → 세션 실패 처리
        try:
            from app.db.client import get_supabase
            get_supabase().table("sell_sessions").update({
                "status": "publishing_failed",
            }).eq("id", session_id).execute()
        except Exception as e:
            logger.error(
                "session_failure_update_failed session=%s error=%s",
                session_id, e, exc_info=True,
            )
