"""공통 유틸리티 — 레이어 무관 순수 함수."""
from __future__ import annotations

from typing import Any


def safe_int(value: Any, default: int = 0) -> int:
    """정수 변환. 실패 시 default 반환."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
