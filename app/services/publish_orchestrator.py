"""
PublishOrchestrator — 게시 준비·실행·실패 복구 오케스트레이션.

SessionService에서 분리된 게시 관련 워크플로우.
"""
from __future__ import annotations

import logging
from typing import Any

from app.core.utils import safe_int as _safe_int
from app.db.publish_job_repository import PublishJobRepository
from app.domain.exceptions import InvalidUserInputError
from app.repositories.session_repository import SessionRepository
from app.services.publish_service import PublishService
from app.services.recovery_service import RecoveryService
from app.services.session_meta import (
    set_publish_complete,
    set_publish_diagnostics,
    set_publish_prepared,
)
from app.services.session_ui import build_session_ui_response

logger = logging.getLogger(__name__)

# 서버 Playwright 게시 불가 → 크롬 익스텐션 전용 플랫폼
EXTENSION_ONLY_PLATFORMS = {"joongna"}


class PublishOrchestrator:
    def __init__(
        self,
        session_repository: SessionRepository,
        publish_service: PublishService,
        recovery_service: RecoveryService,
        job_repo: PublishJobRepository | None = None,
    ):
        self.repo = session_repository
        self.publish_service = publish_service
        self.recovery_service = recovery_service
        self.job_repo = job_repo or PublishJobRepository()

    async def prepare_publish(
        self,
        session_id: str,
        session: dict[str, Any],
        current_status: str,
        platform_targets: list[str],
    ) -> dict[str, Any]:
        """게시 준비: 플랫폼 패키지 생성."""
        if not platform_targets:
            raise InvalidUserInputError("플랫폼을 선택해주세요")

        listing_data = dict(session.get("listing_data_jsonb") or {})
        canonical = listing_data.get("canonical_listing") or {}
        if _safe_int(canonical.get("price"), 0) <= 0:
            raise InvalidUserInputError("유효한 가격이 없습니다. 판매글을 다시 생성해주세요.")

        listing_data["platform_packages"] = self.publish_service.build_platform_packages(
            canonical_listing=canonical, platform_targets=platform_targets,
        )

        workflow_meta = dict(session.get("workflow_meta_jsonb") or {})
        set_publish_prepared(workflow_meta)

        from app.domain.exceptions import InvalidStateTransitionError, SessionUpdateError
        updated = self._update_or_raise(session_id, {
            "status": "awaiting_publish_approval",
            "selected_platforms_jsonb": platform_targets,
            "listing_data_jsonb": listing_data,
            "workflow_meta_jsonb": workflow_meta,
        }, expected_status=current_status)
        return build_session_ui_response(updated)

    async def publish_session(
        self,
        session_id: str,
        session: dict[str, Any],
        current_status: str,
        user_id: str | None = None,
    ) -> dict[str, Any]:
        """게시 실행. PUBLISH_USE_QUEUE 설정에 따라 큐/직접 실행 분기."""
        from app.core.config import settings
        if settings.publish_use_queue:
            return await self._publish_via_queue(
                session_id, session, current_status, user_id,
            )
        return await self.publish_session_sync(
            session_id, session, current_status,
        )

    async def _publish_via_queue(
        self,
        session_id: str,
        session: dict[str, Any],
        current_status: str,
        user_id: str | None = None,
    ) -> dict[str, Any]:
        """Job Queue에 등록하고 즉시 반환. 실제 실행은 PublishWorker가 처리."""
        selected = session.get("selected_platforms_jsonb") or []
        packages = (session.get("listing_data_jsonb") or {}).get("platform_packages") or {}
        if not selected:
            raise InvalidUserInputError("선택된 플랫폼이 없습니다")

        workflow_meta = dict(session.get("workflow_meta_jsonb") or {})

        # 익스텐션 전용 플랫폼 분리
        server_platforms = [p for p in selected if p not in EXTENSION_ONLY_PLATFORMS]
        extension_platforms = [p for p in selected if p in EXTENSION_ONLY_PLATFORMS]

        # 익스텐션 전용 플랫폼은 즉시 결과 기록
        if extension_platforms:
            publish_results = dict(workflow_meta.get("publish_results") or {})
            for p in extension_platforms:
                publish_results[p] = {
                    "success": False,
                    "source": "extension_required",
                    "error_message": "크롬 익스텐션에서 게시해주세요.",
                }
            workflow_meta["publish_results"] = publish_results

        # 서버 게시 플랫폼이 없으면 바로 completed
        if not server_platforms:
            self._update_or_raise(
                session_id,
                {"status": "completed", "workflow_meta_jsonb": workflow_meta},
                expected_status=current_status,
            )
            updated = self.repo.get_by_id(session_id)
            return build_session_ui_response(updated or session)

        self._update_or_raise(
            session_id,
            {"status": "publishing", "workflow_meta_jsonb": workflow_meta},
            expected_status=current_status,
        )

        # 서버 플랫폼만 Job Queue에 등록
        jobs = self.job_repo.create_batch(
            session_id=session_id,
            user_id=user_id or session.get("user_id", ""),
            platforms=server_platforms,
            packages=packages,
        )
        logger.info(
            "publish_jobs_enqueued session=%s platforms=%s job_count=%d",
            session_id, server_platforms, len(jobs),
        )

        updated = self.repo.get_by_id(session_id)
        return build_session_ui_response(updated or session)

    async def publish_session_sync(
        self,
        session_id: str,
        session: dict[str, Any],
        current_status: str,
    ) -> dict[str, Any]:
        """동기 게시 실행 (기존 방식 — fallback용).

        Job Queue 없이 직접 Playwright 실행. 개발/테스트 환경에서 사용.
        """
        selected = session.get("selected_platforms_jsonb") or []
        packages = (session.get("listing_data_jsonb") or {}).get("platform_packages") or {}
        if not selected:
            raise InvalidUserInputError("선택된 플랫폼이 없습니다")

        workflow_meta = dict(session.get("workflow_meta_jsonb") or {})
        self._update_or_raise(
            session_id,
            {"status": "publishing", "workflow_meta_jsonb": workflow_meta},
            expected_status=current_status,
        )

        # 익스텐션 전용 플랫폼 분리
        server_platforms = [p for p in selected if p not in EXTENSION_ONLY_PLATFORMS]
        extension_platforms = [p for p in selected if p in EXTENSION_ONLY_PLATFORMS]

        publish_results: dict[str, Any] = {}

        # 익스텐션 전용 플랫폼은 서버 게시 스킵 → 안내 메시지
        for p in extension_platforms:
            publish_results[p] = {
                "success": False,
                "source": "extension_required",
                "error_message": "크롬 익스텐션에서 게시해주세요.",
            }

        # 서버 게시 대상만 실제 Playwright 실행
        any_failure = False
        if server_platforms:
            server_results, any_failure = await self.publish_service.execute_publish(
                server_platforms, packages,
            )
            publish_results.update(server_results)

        set_publish_complete(workflow_meta, publish_results)

        any_success = any(r.get("success") for r in publish_results.values())

        # extension_required는 실패로 치지 않음
        real_failures = {
            p: r for p, r in publish_results.items()
            if not r.get("success") and r.get("source") != "extension_required"
        }

        if any_failure:
            await self._handle_publish_failure(session_id, workflow_meta, publish_results)

        # 서버 게시 플랫폼이 없거나 성공한 게 있거나 실패가 없으면 completed
        if not server_platforms or any_success or not real_failures:
            final_status = "completed"
        else:
            final_status = "publishing_failed"

        payload: dict[str, Any] = {"status": final_status, "workflow_meta_jsonb": workflow_meta}
        updated = self._update_or_raise(session_id, payload)
        return build_session_ui_response(updated)

    async def _handle_publish_failure(
        self, session_id: str, workflow_meta: dict[str, Any], publish_results: dict[str, Any],
    ) -> None:
        """게시 실패 시 recovery + Discord 알림."""
        product_data = (self.repo.get_by_id(session_id) or {}).get("product_data_jsonb") or {}
        recovery_result = self.recovery_service.run_recovery(
            session_id=session_id, product_data=product_data, publish_results=publish_results,
        )
        set_publish_diagnostics(
            workflow_meta, recovery_result["publish_diagnostics"], recovery_result["tool_calls"],
        )

        from app.domain.publish_policy import DISCORD_ALERT_THRESHOLD
        retry_count = workflow_meta.get("publish_retry_count", 0) + 1
        workflow_meta["publish_retry_count"] = retry_count

        if retry_count >= DISCORD_ALERT_THRESHOLD:
            failed_platforms = [p for p, r in publish_results.items() if not r.get("success")]
            await self._send_discord_alert(
                session_id=session_id,
                message=(
                    f"게시 {retry_count}회 연속 실패\n"
                    f"실패 플랫폼: {', '.join(failed_platforms)}\n"
                    f"에러: {publish_results}"
                ),
            )

    async def _send_discord_alert(self, session_id: str, message: str) -> None:
        """Discord 알림 발송. 실패해도 예외를 던지지 않는다."""
        try:
            from app.tools.agentic_tools import discord_alert_tool
            await discord_alert_tool(message=message, session_id=session_id)
            logger.info("discord_alert_sent session=%s", session_id)
        except Exception as e:
            logger.warning("discord_alert_failed session=%s error=%s", session_id, e, exc_info=True)

    def _update_or_raise(
        self, session_id: str, payload: dict[str, Any], expected_status: str | None = None,
    ) -> dict[str, Any]:
        from app.domain.exceptions import InvalidStateTransitionError, SessionUpdateError
        result = self.repo.update(
            session_id=session_id, payload=payload, expected_status=expected_status,
        )
        if not result:
            if expected_status:
                raise InvalidStateTransitionError(
                    f"세션 상태가 변경되었습니다 (expected={expected_status}): {session_id}"
                )
            raise SessionUpdateError(f"세션 업데이트 실패: {session_id}")
        return result
