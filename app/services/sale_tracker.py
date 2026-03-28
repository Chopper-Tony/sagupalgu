"""
SaleTracker — 판매 상태 입력 + 최적화 오케스트레이션.

SessionService에서 분리된 판매 후 처리 워크플로우.
"""
from __future__ import annotations

from typing import Any

from app.domain.exceptions import InvalidUserInputError
from app.repositories.session_repository import SessionRepository
from app.services.optimization_service import OptimizationService
from app.services.session_meta import append_tool_calls, set_sale_status
from app.services.session_ui import build_session_ui_response


class SaleTracker:
    def __init__(
        self,
        session_repository: SessionRepository,
        optimization_service: OptimizationService,
    ):
        self.repo = session_repository
        self.optimization_service = optimization_service

    async def update_sale_status(
        self,
        session_id: str,
        session: dict[str, Any],
        sale_status: str,
    ) -> dict[str, Any]:
        """판매 상태 입력 + 최적화 에이전트 실행."""
        if sale_status not in ("sold", "unsold", "in_progress"):
            raise InvalidUserInputError("sale_status는 sold / unsold / in_progress 중 하나여야 합니다")

        listing_data = dict(session.get("listing_data_jsonb") or {})
        product_data = session.get("product_data_jsonb") or {}
        workflow_meta = dict(session.get("workflow_meta_jsonb") or {})
        set_sale_status(workflow_meta, sale_status)

        opt_result = self.optimization_service.run_post_sale_optimization(
            session_id=session_id, product_data=product_data, listing_data=listing_data,
            sale_status=sale_status, followup_due_at=workflow_meta.get("followup_due_at"),
        )
        optimization = opt_result["optimization_suggestion"]
        if optimization:
            listing_data["optimization_suggestion"] = optimization

        append_tool_calls(workflow_meta, opt_result["tool_calls"])
        final_status = opt_result["status"] or (
            "optimization_suggested" if optimization else "awaiting_sale_status_update"
        )

        payload: dict[str, Any] = {
            "status": final_status,
            "listing_data_jsonb": listing_data,
            "workflow_meta_jsonb": workflow_meta,
        }
        from app.domain.exceptions import SessionUpdateError
        result = self.repo.update(session_id=session_id, payload=payload)
        if not result:
            raise SessionUpdateError(f"세션 업데이트 실패: {session_id}")
        return build_session_ui_response(result)
