"""
PublishOrchestrator — 게시 준비·실행·실패 복구 오케스트레이션.

SessionService에서 분리된 게시 관련 워크플로우.
"""
from __future__ import annotations

import logging
from typing import Any

from app.core.utils import safe_int as _safe_int
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


class PublishOrchestrator:
    def __init__(
        self,
        session_repository: SessionRepository,
        publish_service: PublishService,
        recovery_service: RecoveryService,
    ):
        self.repo = session_repository
        self.publish_service = publish_service
        self.recovery_service = recovery_service

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
    ) -> dict[str, Any]:
        """게시 실행: 플랫폼별 병렬 게시 + 실패 복구."""
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

        publish_results, any_failure = await self.publish_service.execute_publish(selected, packages)
        set_publish_complete(workflow_meta, publish_results)

        final_status = "completed"
        if any_failure:
            await self._handle_publish_failure(session_id, workflow_meta, publish_results)
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
