"""
사구팔구 도메인 예외 계층.

예외 매핑 정책 (전체 프로젝트 단일 기준):
  SessionNotFoundError         → HTTP 404  (세션 없음)
  InvalidStateTransitionError  → HTTP 409  (허용되지 않은 상태 전이)
  ListingGenerationError       → HTTP 500  (판매글 생성 실패)
  ListingRewriteError          → HTTP 500  (판매글 재작성 실패)
  PublishExecutionError        → HTTP 502  (게시 실행 중 복구 불가 오류)

  범용 ValueError              → HTTP 400  (입력 검증 실패 — 위 타입에 해당하지 않는 것)

매핑 적용 위치:
  app/main.py           — 글로벌 exception_handler (FastAPI 앱 레벨)
  app/api/session_router.py — _domain_error 헬퍼 (라우터 레벨 명시)
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
