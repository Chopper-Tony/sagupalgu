"""
SessionService — 세션 라이프사이클 오케스트레이터.

책임:
- 세션 상태 전이 (repo 경유)
- 각 도메인 서비스 / LangGraph 노드 호출 조율
- UI 응답 조립은 build_session_ui_response()에 위임
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.domain.exceptions import SessionNotFoundError
from app.domain.product_rules import needs_user_input, normalize_text
from app.domain.session_status import assert_allowed_transition
from app.repositories.session_repository import SessionRepository
from app.services.optimization_service import OptimizationService
from app.services.product_service import ProductService
from app.services.publish_service import PublishService
from app.services.recovery_service import RecoveryService
from app.services.seller_copilot_service import SellerCopilotService
from app.services.session_meta import (
    append_rewrite_entry,
    append_tool_calls,
    normalize_listing_meta,
    set_analysis_checkpoint,
    set_product_confirmed,
    set_publish_complete,
    set_publish_diagnostics,
    set_publish_prepared,
    set_sale_status,
)
from app.services.session_ui import build_session_ui_response  # noqa: F401 — re-export


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


class SessionService:
    def __init__(
        self,
        session_repository: SessionRepository,
        product_service: "ProductService",
        publish_service: "PublishService",
        copilot_service: "SellerCopilotService",
        recovery_service: "RecoveryService",
        optimization_service: "OptimizationService",
    ):
        self.repo = session_repository
        self.product_service = product_service
        self.publish_service = publish_service
        self.copilot_service = copilot_service
        self.recovery_service = recovery_service
        self.optimization_service = optimization_service

    # ── 세션 생성 / 조회 ───────────────────────────────────────────

    async def create_session(self, user_id: str) -> Dict:
        session = self.repo.create(user_id=user_id)
        return build_session_ui_response(session.to_record())

    async def get_session(self, session_id: str) -> Dict:
        session = self._get_or_raise(session_id)
        return build_session_ui_response(session)

    # ── 이미지 업로드 ──────────────────────────────────────────────

    async def attach_images(self, session_id: str, image_urls: List[str]) -> Dict:
        session = self._ensure_transition(session_id, "images_uploaded")
        product_data = dict(session.get("product_data_jsonb") or {})
        product_data["image_paths"] = image_urls
        updated = self._update_or_raise(session_id, {
            "status": "images_uploaded",
            "product_data_jsonb": product_data,
        })
        return build_session_ui_response(updated)

    # ── 상품 분석 ──────────────────────────────────────────────────

    async def analyze_session(self, session_id: str) -> Dict:
        session = self._ensure_transition(session_id, "awaiting_product_confirmation")

        product_data = dict(session.get("product_data_jsonb") or {})
        image_paths = product_data.get("image_paths") or []
        if not image_paths:
            raise ValueError("이미지가 없습니다")

        result = await self.product_service.identify_product(image_paths)
        candidates = result.candidates or []
        if not candidates:
            raise ValueError("상품 인식 결과가 없습니다")

        top = candidates[0]
        needs_input = needs_user_input(top)

        product_data["candidates"] = candidates
        product_data["analysis_source"] = "vision"
        product_data["image_count"] = len(image_paths)
        product_data["needs_user_input"] = needs_input
        if needs_input:
            product_data["user_input_prompt"] = (
                "사진만으로 모델명을 정확히 식별하지 못했습니다. 모델명을 직접 입력해 주세요."
            )
        else:
            product_data.pop("user_input_prompt", None)

        workflow_meta = dict(session.get("workflow_meta_jsonb") or {})
        set_analysis_checkpoint(workflow_meta, needs_input)

        updated = self._update_or_raise(session_id, {
            "status": "awaiting_product_confirmation",
            "product_data_jsonb": product_data,
            "workflow_meta_jsonb": workflow_meta,
        })
        return build_session_ui_response(updated)

    # ── 상품 확정 ──────────────────────────────────────────────────

    async def confirm_product(self, session_id: str, candidate_index: int) -> Dict:
        session = self._ensure_transition(session_id, "product_confirmed")

        product_data = dict(session.get("product_data_jsonb") or {})
        candidates = product_data.get("candidates") or []
        if not (0 <= candidate_index < len(candidates)):
            raise ValueError("유효하지 않은 후보 인덱스입니다")

        product_data["confirmed_product"] = {**candidates[candidate_index], "source": "vision"}
        product_data["needs_user_input"] = False
        product_data.pop("user_input_prompt", None)

        workflow_meta = dict(session.get("workflow_meta_jsonb") or {})
        set_product_confirmed(workflow_meta)

        updated = self._update_or_raise(session_id, {
            "status": "product_confirmed",
            "product_data_jsonb": product_data,
            "workflow_meta_jsonb": workflow_meta,
        })
        return build_session_ui_response(updated)

    async def provide_product_info(
        self, session_id: str, model: str,
        brand: Optional[str] = None, category: Optional[str] = None,
    ) -> Dict:
        session = self._ensure_transition(session_id, "product_confirmed")

        normalized_model = normalize_text(model)
        if not normalized_model:
            raise ValueError("모델명은 필수입니다")

        product_data = dict(session.get("product_data_jsonb") or {})
        product_data["confirmed_product"] = {
            "brand": normalize_text(brand) or "Unknown",
            "model": normalized_model,
            "category": normalize_text(category) or "unknown",
            "confidence": 1.0,
            "source": "user_input",
        }
        product_data["needs_user_input"] = False
        product_data.pop("user_input_prompt", None)

        workflow_meta = dict(session.get("workflow_meta_jsonb") or {})
        set_product_confirmed(workflow_meta)

        updated = self._update_or_raise(session_id, {
            "status": "product_confirmed",
            "product_data_jsonb": product_data,
            "workflow_meta_jsonb": workflow_meta,
        })
        return build_session_ui_response(updated)

    # ── 판매글 생성 / 재작성 ────────────────────────────────────────

    async def generate_listing(self, session_id: str) -> Dict:
        session = self._ensure_transition(session_id, "draft_generated")

        result_payload = await self.copilot_service.run_listing_pipeline(
            session_id=session_id,
            session_record=session,
        )

        listing_data = dict(result_payload.get("listing_data_jsonb") or {})
        listing_data.pop("platform_packages", None)

        workflow_meta = dict(result_payload.get("workflow_meta_jsonb") or {})
        normalize_listing_meta(workflow_meta, result_payload.get("tool_calls") or [])

        updated = self._update_or_raise(session_id, {
            "status": "draft_generated",
            "selected_platforms_jsonb": [],
            "product_data_jsonb": result_payload.get("product_data_jsonb") or {},
            "listing_data_jsonb": listing_data,
            "workflow_meta_jsonb": workflow_meta,
        })
        return build_session_ui_response(updated)

    async def rewrite_listing(self, session_id: str, instruction: str) -> Dict:
        session = self._ensure_transition(session_id, "draft_generated")

        if not instruction or not instruction.strip():
            raise ValueError("재작성 지시사항이 필요합니다")

        result_payload = await self.copilot_service.run_rewrite_pipeline(
            session_id=session_id,
            session_record=session,
            rewrite_instruction=instruction.strip(),
        )

        listing_data = dict(result_payload.get("listing_data_jsonb") or {})
        listing_data.pop("platform_packages", None)

        workflow_meta = dict(session.get("workflow_meta_jsonb") or {})
        append_rewrite_entry(workflow_meta, instruction, result_payload.get("tool_calls") or [])

        updated = self._update_or_raise(session_id, {
            "status": "draft_generated",
            "listing_data_jsonb": listing_data,
            "workflow_meta_jsonb": workflow_meta,
        })
        return build_session_ui_response(updated)

    # ── 게시 준비 / 게시 ───────────────────────────────────────────

    async def prepare_publish(self, session_id: str, platform_targets: List[str]) -> Dict:
        session = self._ensure_transition(session_id, "awaiting_publish_approval")

        if not platform_targets:
            raise ValueError("플랫폼을 선택해주세요")

        listing_data = dict(session.get("listing_data_jsonb") or {})
        canonical = listing_data.get("canonical_listing") or {}

        if _safe_int(canonical.get("price"), 0) <= 0:
            raise ValueError("유효한 가격이 없습니다. 판매글을 다시 생성해주세요.")

        listing_data["platform_packages"] = self.publish_service.build_platform_packages(
            canonical_listing=canonical,
            platform_targets=platform_targets,
        )

        workflow_meta = dict(session.get("workflow_meta_jsonb") or {})
        set_publish_prepared(workflow_meta)

        updated = self._update_or_raise(session_id, {
            "status": "awaiting_publish_approval",
            "selected_platforms_jsonb": platform_targets,
            "listing_data_jsonb": listing_data,
            "workflow_meta_jsonb": workflow_meta,
        })
        return build_session_ui_response(updated)

    async def publish_session(self, session_id: str) -> Dict:
        session = self._ensure_transition(session_id, "publishing")

        selected = session.get("selected_platforms_jsonb") or []
        packages = (session.get("listing_data_jsonb") or {}).get("platform_packages") or {}

        if not selected:
            raise ValueError("선택된 플랫폼이 없습니다")

        workflow_meta = dict(session.get("workflow_meta_jsonb") or {})
        self._update_or_raise(session_id, {"status": "publishing", "workflow_meta_jsonb": workflow_meta})

        publish_results, any_failure = await self.publish_service.execute_publish(selected, packages)

        set_publish_complete(workflow_meta, publish_results)

        if any_failure:
            product_data = (self.repo.get_by_id(session_id) or {}).get("product_data_jsonb") or {}
            recovery_result = self.recovery_service.run_recovery(
                session_id=session_id,
                product_data=product_data,
                publish_results=publish_results,
            )
            set_publish_diagnostics(
                workflow_meta,
                recovery_result["publish_diagnostics"],
                recovery_result["tool_calls"],
            )
            final_status = "publishing_failed"
        else:
            final_status = "completed"

        updated = self._update_or_raise(session_id, {
            "status": final_status,
            "workflow_meta_jsonb": workflow_meta,
        })
        return build_session_ui_response(updated)

    # ── 판매 상태 입력 ─────────────────────────────────────────────

    async def update_sale_status(self, session_id: str, sale_status: str) -> Dict:
        if sale_status not in ("sold", "unsold", "in_progress"):
            raise ValueError("sale_status는 sold / unsold / in_progress 중 하나여야 합니다")

        session = self._get_or_raise(session_id)
        listing_data = dict(session.get("listing_data_jsonb") or {})
        product_data = session.get("product_data_jsonb") or {}
        workflow_meta = dict(session.get("workflow_meta_jsonb") or {})
        set_sale_status(workflow_meta, sale_status)

        opt_result = self.optimization_service.run_post_sale_optimization(
            session_id=session_id,
            product_data=product_data,
            listing_data=listing_data,
            sale_status=sale_status,
            followup_due_at=workflow_meta.get("followup_due_at"),
        )
        optimization = opt_result["optimization_suggestion"]
        if optimization:
            listing_data["optimization_suggestion"] = optimization

        append_tool_calls(workflow_meta, opt_result["tool_calls"])
        final_status = opt_result["status"] or (
            "optimization_suggested" if optimization else "awaiting_sale_status_update"
        )

        updated = self._update_or_raise(session_id, {
            "status": final_status,
            "listing_data_jsonb": listing_data,
            "workflow_meta_jsonb": workflow_meta,
        })
        return build_session_ui_response(updated)

    # ── 내부 헬퍼 ────────────────────────────────────────────────

    def _get_or_raise(self, session_id: str) -> Dict:
        session = self.repo.get_by_id(session_id)
        if not session:
            raise SessionNotFoundError(f"세션을 찾을 수 없습니다: {session_id}")
        return session

    def _update_or_raise(self, session_id: str, payload: Dict) -> Dict:
        result = self.repo.update(session_id=session_id, payload=payload)
        if not result:
            raise ValueError(f"세션 업데이트 실패: {session_id}")
        return result

    def _ensure_transition(self, session_id: str, next_status: str) -> Dict:
        """세션 조회 + 상태 전이 유효성 검증을 한 번에 수행한다."""
        session = self._get_or_raise(session_id)
        assert_allowed_transition(session["status"], next_status)
        return session


