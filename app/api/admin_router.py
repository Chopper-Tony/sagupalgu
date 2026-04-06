"""
Admin API — 게시 Job Queue 운영 엔드포인트.

운영자 수동 제어:
- 큐 상태 조회
- job 재시도 / 강제 fail
- 플랫폼 일시중지
- 사용자 게시 비활성화
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])


def _verify_admin_key(request: Request) -> None:
    """X-Admin-Key 헤더로 admin 인증. 키 미설정 시 접근 차단."""
    from app.core.config import settings
    admin_key = settings.admin_api_key
    if not admin_key:
        raise HTTPException(status_code=403, detail="Admin API가 비활성화되어 있습니다")
    provided = request.headers.get("X-Admin-Key", "")
    if provided != admin_key:
        raise HTTPException(status_code=403, detail="유효하지 않은 Admin API 키입니다")


def _get_job_repo():
    from app.db.publish_job_repository import PublishJobRepository
    return PublishJobRepository()


@router.get("/publish-queue/stats", dependencies=[Depends(_verify_admin_key)])
async def queue_stats() -> dict[str, Any]:
    """큐 상태 통계."""
    return _get_job_repo().get_queue_stats()


@router.get("/publish-queue/jobs", dependencies=[Depends(_verify_admin_key)])
async def list_jobs(
    session_id: str | None = None,
    status: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """작업 목록 조회."""
    repo = _get_job_repo()
    if session_id:
        return repo.get_by_session(session_id)
    if status:
        result = (
            repo._get_client()
            .table("publish_jobs")
            .select("*")
            .eq("status", status)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        return result.data or []
    result = (
        repo._get_client()
        .table("publish_jobs")
        .select("*")
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return result.data or []


@router.get("/publish-queue/jobs/{job_id}", dependencies=[Depends(_verify_admin_key)])
async def get_job(job_id: str) -> dict[str, Any]:
    """개별 작업 조회."""
    job = _get_job_repo().get_by_id(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.post("/publish-queue/jobs/{job_id}/retry", dependencies=[Depends(_verify_admin_key)])
async def retry_job(job_id: str) -> dict[str, Any]:
    """실패한 작업을 재시도 대기열에 넣는다."""
    repo = _get_job_repo()
    job = repo.get_by_id(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job["status"] not in ("failed", "cancelled"):
        raise HTTPException(
            status_code=400,
            detail=f"재시도 불가능한 상태: {job['status']}",
        )

    from datetime import datetime, timezone
    repo._get_client().table("publish_jobs").update({
        "status": "pending",
        "error_code": None,
        "error_message": None,
        "locked_by": None,
        "locked_at": None,
        "next_retry_at": None,
    }).eq("id", job_id).execute()

    logger.info("admin_job_retry job_id=%s", job_id)
    return {"job_id": job_id, "status": "pending", "message": "재시도 대기열에 추가됨"}


@router.post("/publish-queue/jobs/{job_id}/force-fail", dependencies=[Depends(_verify_admin_key)])
async def force_fail_job(job_id: str) -> dict[str, Any]:
    """stuck 작업을 강제 실패 처리."""
    repo = _get_job_repo()
    job = repo.get_by_id(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job["status"] in ("completed", "failed", "cancelled"):
        raise HTTPException(
            status_code=400,
            detail=f"이미 종료된 작업: {job['status']}",
        )

    repo.fail(
        job_id,
        error_code="admin_force_fail",
        error_message="운영자 강제 실패 처리",
        auto_recoverable=False,
    )
    logger.info("admin_job_force_fail job_id=%s", job_id)
    return {"job_id": job_id, "status": "failed", "message": "강제 실패 처리됨"}


@router.post("/publish-queue/platforms/{platform}/pause", dependencies=[Depends(_verify_admin_key)])
async def pause_platform(platform: str) -> dict[str, Any]:
    """특정 플랫폼의 대기 중 작업을 일시 중지."""
    if platform not in ("bunjang", "joongna", "daangn"):
        raise HTTPException(status_code=400, detail=f"유효하지 않은 플랫폼: {platform}")
    count = _get_job_repo().pause_platform(platform)
    return {"platform": platform, "cancelled_count": count, "message": f"{platform} 일시중지"}


@router.post("/publish-queue/users/{user_id}/disable", dependencies=[Depends(_verify_admin_key)])
async def disable_user_publishing(user_id: str) -> dict[str, Any]:
    """특정 사용자의 대기 중 게시 작업을 모두 취소."""
    count = _get_job_repo().disable_user_publishing(user_id)
    return {"user_id": user_id, "cancelled_count": count, "message": "게시 비활성화"}


@router.post("/publish-queue/release-stuck", dependencies=[Depends(_verify_admin_key)])
async def release_stuck_jobs() -> dict[str, Any]:
    """stuck 작업 일괄 해제."""
    count = _get_job_repo().release_stuck_jobs()
    return {"released_count": count, "message": f"{count}개 stuck 작업 해제"}
