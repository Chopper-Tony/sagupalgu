"""
게시 신뢰성 정책 — 타임아웃·재시도·에러 분류.

PublishService와 recovery_tools에서 참조하는 단일 진실 원천.
"""
from __future__ import annotations

from typing import Any, Dict

# ── 타임아웃 (초) ────────────────────────────────────────────────

PUBLISH_TIMEOUT_SECONDS: int = 180  # 플랫폼별 게시 최대 대기 (이미지 업로드+폼 입력 포함)
MAX_CONCURRENT_BROWSERS: int = 2   # Playwright 브라우저 동시 실행 상한 (메모리 보호)

# ── 재시도 정책 ──────────────────────────────────────────────────

MAX_PUBLISH_RETRIES: int = 2
RETRY_BASE_DELAY_SECONDS: float = 5.0  # 지수 백오프 기저 (5, 10, 20…)
DISCORD_ALERT_THRESHOLD: int = 3  # 이 횟수 이상 실패 시 Discord 알림 발송

# ── 에러 분류 (Failure Taxonomy) ─────────────────────────────────

# error_code → {category, auto_recoverable, description}
FAILURE_TAXONOMY: Dict[str, Dict[str, Any]] = {
    "timeout": {
        "category": "network",
        "auto_recoverable": True,
        "description": "게시 타임아웃 초과",
    },
    "network_error": {
        "category": "network",
        "auto_recoverable": True,
        "description": "네트워크 연결 오류",
    },
    "login_expired": {
        "category": "auth",
        "auto_recoverable": False,
        "description": "로그인 세션 만료 — 수동 갱신 필요",
    },
    "content_policy": {
        "category": "content",
        "auto_recoverable": False,
        "description": "플랫폼 콘텐츠 정책 위반",
    },
    "missing_platform_package": {
        "category": "config",
        "auto_recoverable": False,
        "description": "플랫폼 패키지 누락",
    },
    "credential_missing": {
        "category": "config",
        "auto_recoverable": False,
        "description": "플랫폼 인증 정보 미설정",
    },
    "platform_unavailable": {
        "category": "external",
        "auto_recoverable": True,
        "description": "플랫폼 서버 점검 또는 일시 장애",
    },
    "image_upload_failed": {
        "category": "content",
        "auto_recoverable": True,
        "description": "이미지 업로드 실패",
    },
    "category_selection_failed": {
        "category": "ui",
        "auto_recoverable": True,
        "description": "카테고리 선택 실패 — 재시도 권장",
    },
    "form_validation_failed": {
        "category": "content",
        "auto_recoverable": True,
        "description": "폼 필수값 검증 오류",
    },
    "publish_exception": {
        "category": "unknown",
        "auto_recoverable": False,
        "description": "예상치 못한 게시 오류",
    },
}


def classify_error(error_code: str, error_message: str = "") -> Dict[str, Any]:
    """에러 코드와 메시지를 분류한다. 알 수 없으면 publish_exception으로 분류."""
    # 정확한 코드 매칭
    if error_code in FAILURE_TAXONOMY:
        return {**FAILURE_TAXONOMY[error_code], "error_code": error_code}

    # 메시지 기반 추론
    msg = error_message.lower()
    if "timeout" in msg or "timed out" in msg:
        return {**FAILURE_TAXONOMY["timeout"], "error_code": "timeout"}
    if "login" in msg or "auth" in msg or "session" in msg:
        return {**FAILURE_TAXONOMY["login_expired"], "error_code": "login_expired"}
    if "network" in msg or "connection" in msg or "dns" in msg:
        return {**FAILURE_TAXONOMY["network_error"], "error_code": "network_error"}
    if "policy" in msg or "content" in msg or "blocked" in msg:
        return {**FAILURE_TAXONOMY["content_policy"], "error_code": "content_policy"}
    if "503" in msg or "502" in msg or "maintenance" in msg:
        return {**FAILURE_TAXONOMY["platform_unavailable"], "error_code": "platform_unavailable"}
    if "이미지" in msg and ("업로드" in msg or "필수" in msg or "찾지 못" in msg):
        return {**FAILURE_TAXONOMY["image_upload_failed"], "error_code": "image_upload_failed"}
    if "카테고리" in msg and ("선택" in msg or "실패" in msg):
        return {**FAILURE_TAXONOMY["category_selection_failed"], "error_code": "category_selection_failed"}
    if "검증" in msg or ("글쓰기 페이지" in msg and "머뭄" in msg):
        return {**FAILURE_TAXONOMY["form_validation_failed"], "error_code": "form_validation_failed"}

    return {**FAILURE_TAXONOMY["publish_exception"], "error_code": "publish_exception"}


def get_retry_delay(attempt: int) -> float:
    """지수 백오프 대기 시간을 반환한다 (attempt는 0부터 시작)."""
    return RETRY_BASE_DELAY_SECONDS * (2 ** attempt)
