"""
사구팔구 도메인 예외 계층.

HTTP 매핑:
  SessionNotFoundError         → 404
  InvalidStateTransitionError  → 409
  ListingGenerationError        → 500
  ListingRewriteError           → 500
  PublishExecutionError         → 502
"""
from __future__ import annotations


class SagupalguError(Exception):
    """사구팔구 도메인 기본 예외."""


class SessionNotFoundError(SagupalguError):
    """요청한 세션이 존재하지 않음."""


class InvalidStateTransitionError(SagupalguError):
    """현재 상태에서 허용되지 않는 전이 시도."""


class ListingGenerationError(SagupalguError):
    """판매글 최초 생성 실패."""


class ListingRewriteError(SagupalguError):
    """판매글 재작성 실패."""


class PublishExecutionError(SagupalguError):
    """게시 실행 중 복구 불가능한 오류 발생."""
