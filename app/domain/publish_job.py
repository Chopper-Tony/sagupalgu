"""
Publish Job 도메인 모델.

API-워커 분리를 위한 Job Queue 상태 모델.
publish_jobs 테이블의 단일 진실 원천(SSOT).
"""
from __future__ import annotations

from enum import Enum


class PublishJobStatus(str, Enum):
    """게시 작업 상태."""

    PENDING = "pending"  # 대기 중 (큐에 등록)
    CLAIMED = "claimed"  # 워커가 점유
    RUNNING = "running"  # 실행 중
    COMPLETED = "completed"  # 성공
    FAILED = "failed"  # 실패 (재시도 불가)
    RETRY_SCHEDULED = "retry_scheduled"  # 재시도 대기
    CANCELLED = "cancelled"  # 수동 취소


# 상태 전이 규칙
ALLOWED_JOB_TRANSITIONS: dict[str, set[str]] = {
    PublishJobStatus.PENDING: {
        PublishJobStatus.CLAIMED,
        PublishJobStatus.CANCELLED,
    },
    PublishJobStatus.CLAIMED: {
        PublishJobStatus.RUNNING,
        PublishJobStatus.FAILED,  # claim 후 즉시 실패 (lock 충돌 등)
        PublishJobStatus.CANCELLED,
    },
    PublishJobStatus.RUNNING: {
        PublishJobStatus.COMPLETED,
        PublishJobStatus.FAILED,
        PublishJobStatus.RETRY_SCHEDULED,
    },
    PublishJobStatus.RETRY_SCHEDULED: {
        PublishJobStatus.PENDING,  # 재시도 시점에 다시 pending으로
        PublishJobStatus.CANCELLED,
    },
    PublishJobStatus.COMPLETED: set(),  # 터미널
    PublishJobStatus.FAILED: set(),  # 터미널
    PublishJobStatus.CANCELLED: set(),  # 터미널
}

TERMINAL_STATUSES = {
    PublishJobStatus.COMPLETED,
    PublishJobStatus.FAILED,
    PublishJobStatus.CANCELLED,
}

# 워커 설정 상수
WORKER_POLL_INTERVAL_SECONDS = 3.0
WORKER_LOCK_TIMEOUT_SECONDS = 300.0  # lock 5분 초과 시 stuck 판정
DEFAULT_MAX_ATTEMPTS = 3

# 단계별 타임아웃 (초)
STEP_TIMEOUTS = {
    "login_check": 15,
    "image_upload": 30,
    "form_fill": 30,
    "category_select": 20,
    "submit": 30,
    "verify": 15,
    "total": 180,
}
