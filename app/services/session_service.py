"""
SessionService — 세션 라이프사이클 오케스트레이터.

책임:
- 세션 상태 전이 (repo 경유)
- 각 도메인 서비스 / LangGraph 노드 호출 조율
- 데이터 조작은 순수 함수에 위임:
  - product_data → session_product.py
  - workflow_meta → session_meta.py
  - UI 응답 → session_ui.py
"""
from __future__ import annotations

from typing import Any

from app.core.utils import safe_int as _safe_int
from app.domain.exceptions import (
    InvalidStateTransitionError,
    InvalidUserInputError,
    SessionNotFoundError,
    SessionUpdateError,
)
from app.domain.session_status import assert_allowed_transition
from app.repositories.session_repository import SessionRepository
from app.services.product_service import ProductService
from app.services.publish_orchestrator import PublishOrchestrator
from app.services.sale_tracker import SaleTracker
from app.services.seller_copilot_service import SellerCopilotService
from app.services.session_meta import (
    append_rewrite_entry,
    normalize_listing_meta,
    set_analysis_checkpoint,
    set_product_confirmed,
)
from app.services.session_product import (
    apply_analysis_result,
    attach_image_paths,
    confirm_from_candidate,
    confirm_from_user_input,
)
from app.services.session_ui import build_session_ui_response  # noqa: F401 — re-export


class SessionService:
    def __init__(
        self,
        session_repository: SessionRepository,
        product_service: "ProductService",
        publish_orchestrator: "PublishOrchestrator",
        copilot_service: "SellerCopilotService",
        sale_tracker: "SaleTracker",
    ):
        self.repo = session_repository
        self.product_service = product_service
        self.publish_orchestrator = publish_orchestrator
        self.copilot_service = copilot_service
        self.sale_tracker = sale_tracker

    # ── 세션 생성 / 조회 ───────────────────────────────────────────

    async def create_session(self, user_id: str) -> dict[str, Any]:
        session = self.repo.create(user_id=user_id)
        return build_session_ui_response(session.to_record())

    async def get_session(self, session_id: str, user_id: str | None = None) -> dict[str, Any]:
        return build_session_ui_response(self._get_or_raise(session_id, user_id))

    async def relist_session(
        self, session_id: str, user_id: str, new_price: int | None = None,
    ) -> dict[str, Any]:
        """기존 세션을 복제하여 새 세션을 생성한다 (재등록)."""
        original = self._get_or_raise(session_id, user_id)

        # 새 세션 생성
        new_session = self.repo.create(user_id=user_id)

        # 기존 데이터 복사
        product_data = dict(original.get("product_data_jsonb") or {})
        listing_data = dict(original.get("listing_data_jsonb") or {})

        # 가격 조정 (옵션)
        if new_price is not None:
            canonical = listing_data.get("canonical_listing") or {}
            canonical["price"] = new_price
            listing_data["canonical_listing"] = canonical

        # sale_status 초기화 (새 상품이므로 available)
        listing_data.pop("sale_status", None)

        # 재등록 출처 기록
        workflow_meta: dict[str, Any] = {
            "schema_version": 1,
            "relisted_from": session_id,
        }

        payload: dict[str, Any] = {
            "status": "completed",
            "product_data_jsonb": product_data,
            "listing_data_jsonb": listing_data,
            "workflow_meta_jsonb": workflow_meta,
        }
        result = self.repo.update(new_session.id, payload)
        if not result:
            raise SessionUpdateError(f"재등록 세션 업데이트 실패: {new_session.id}")

        return build_session_ui_response(result)

    # ── 이미지 업로드 ──────────────────────────────────────────────

    async def attach_images(self, session_id: str, image_urls: list[str], user_id: str | None = None) -> dict[str, Any]:
        session = self._ensure_transition(session_id, "images_uploaded", user_id)
        product_data = dict(session.get("product_data_jsonb") or {})
        attach_image_paths(product_data, image_urls)
        return self._persist_and_respond(
            session_id, "images_uploaded",
            expected_status=session["status"],
            product_data=product_data,
        )

    # ── 상품 분석 ──────────────────────────────────────────────────

    async def analyze_session(self, session_id: str, user_id: str | None = None) -> dict[str, Any]:
        session = self._ensure_transition(session_id, "awaiting_product_confirmation", user_id)

        product_data = dict(session.get("product_data_jsonb") or {})
        image_paths = product_data.get("image_paths") or []
        if not image_paths:
            raise InvalidUserInputError("이미지가 없습니다")

        result = await self.product_service.identify_product(image_paths)
        product_data, needs_input = apply_analysis_result(
            product_data, result.candidates or [], image_paths,
        )

        workflow_meta = dict(session.get("workflow_meta_jsonb") or {})
        set_analysis_checkpoint(workflow_meta, needs_input)

        return self._persist_and_respond(
            session_id, "awaiting_product_confirmation",
            expected_status=session["status"],
            product_data=product_data, workflow_meta=workflow_meta,
        )

    # ── 상품 확정 ──────────────────────────────────────────────────

    async def confirm_product(self, session_id: str, candidate_index: int, user_id: str | None = None) -> dict[str, Any]:
        session = self._ensure_transition(session_id, "product_confirmed", user_id)
        product_data = dict(session.get("product_data_jsonb") or {})
        confirm_from_candidate(product_data, candidate_index)

        workflow_meta = dict(session.get("workflow_meta_jsonb") or {})
        set_product_confirmed(workflow_meta)

        return self._persist_and_respond(
            session_id, "product_confirmed",
            expected_status=session["status"],
            product_data=product_data, workflow_meta=workflow_meta,
        )

    async def provide_product_info(
        self, session_id: str, model: str,
        brand: str | None = None, category: str | None = None,
        user_id: str | None = None,
    ) -> dict[str, Any]:
        session = self._ensure_transition(session_id, "product_confirmed", user_id)
        product_data = dict(session.get("product_data_jsonb") or {})
        confirm_from_user_input(product_data, model, brand, category)

        workflow_meta = dict(session.get("workflow_meta_jsonb") or {})
        set_product_confirmed(workflow_meta)

        return self._persist_and_respond(
            session_id, "product_confirmed",
            expected_status=session["status"],
            product_data=product_data, workflow_meta=workflow_meta,
        )

    # ── 판매글 생성 / 재작성 ────────────────────────────────────────

    async def generate_listing(self, session_id: str, user_id: str | None = None) -> dict[str, Any]:
        session = self._ensure_transition(session_id, "draft_generated", user_id)
        current_status = session["status"]

        result_payload = await self.copilot_service.run_listing_pipeline(
            session_id=session_id, session_record=session,
        )

        listing_data = dict(result_payload.get("listing_data_jsonb") or {})
        listing_data.pop("platform_packages", None)

        # LangGraph 실패 시 직접 LLM 호출 fallback
        if not listing_data.get("canonical_listing"):
            listing_data = await self._fallback_generate_listing(session, listing_data)

        workflow_meta = dict(result_payload.get("workflow_meta_jsonb") or {})
        normalize_listing_meta(workflow_meta, result_payload.get("tool_calls") or [])

        updated = self._update_or_raise(session_id, {
            "status": "draft_generated",
            "selected_platforms_jsonb": [],
            "product_data_jsonb": result_payload.get("product_data_jsonb") or {},
            "listing_data_jsonb": listing_data,
            "workflow_meta_jsonb": workflow_meta,
        }, expected_status=current_status)
        return build_session_ui_response(updated)

    async def _fallback_generate_listing(self, session: dict[str, Any], listing_data: dict[str, Any]) -> dict[str, Any]:
        """LangGraph 파이프라인이 canonical_listing을 생성하지 못했을 때 직접 LLM 호출."""
        import logging
        logger = logging.getLogger(__name__)
        logger.warning("LangGraph listing 생성 실패 — 직접 LLM fallback")

        product_data = session.get("product_data_jsonb") or {}
        confirmed = product_data.get("confirmed_product") or {}
        market_context = listing_data.get("market_context") or {}
        image_paths = product_data.get("image_paths") or []

        brand = confirmed.get("brand", "")
        model = confirmed.get("model", "")
        category = confirmed.get("category", "")
        median_price = market_context.get("median_price") or 0

        # 가격 전략
        from app.services.listing_prompt import build_pricing_strategy
        strategy = build_pricing_strategy(median_price, goal="balanced")
        listing_data["strategy"] = strategy

        # 직접 LLM 판매글 생성 시도
        try:
            from app.services.listing_llm import generate_copy
            result = await generate_copy(
                confirmed_product=confirmed,
                market_context=market_context,
                strategy=strategy,
                image_paths=image_paths,
            )
            if result and result.get("title"):
                # 가격이 0이면 strategy 추천가로 보정
                if not result.get("price") or result["price"] <= 0:
                    result["price"] = strategy.get("recommended_price", median_price)
                listing_data["canonical_listing"] = result
                logger.info("fallback_listing_success title=%s price=%s", result.get("title"), result.get("price"))
                return listing_data
        except Exception as e:
            logger.warning("fallback LLM failed: %s", e, exc_info=True)

        # LLM도 실패하면 템플릿 판매글
        from app.services.listing_llm import build_template_copy
        template = build_template_copy(confirmed, strategy, image_paths)
        if not template.get("price") or template["price"] <= 0:
            template["price"] = strategy.get("recommended_price", median_price)
        listing_data["canonical_listing"] = template
        logger.info("fallback_template_used title=%s price=%s", template.get("title"), template.get("price"))
        return listing_data

    async def rewrite_listing(self, session_id: str, instruction: str, user_id: str | None = None) -> dict[str, Any]:
        session = self._ensure_transition(session_id, "draft_generated", user_id)
        current_status = session["status"]
        if not instruction or not instruction.strip():
            raise InvalidUserInputError("재작성 지시사항이 필요합니다")

        result_payload = await self.copilot_service.run_rewrite_pipeline(
            session_id=session_id, session_record=session,
            rewrite_instruction=instruction.strip(),
        )

        listing_data = dict(result_payload.get("listing_data_jsonb") or {})
        listing_data.pop("platform_packages", None)

        workflow_meta = dict(session.get("workflow_meta_jsonb") or {})
        append_rewrite_entry(workflow_meta, instruction, result_payload.get("tool_calls") or [])

        return self._persist_and_respond(
            session_id, "draft_generated",
            expected_status=current_status,
            listing_data=listing_data, workflow_meta=workflow_meta,
        )

    async def update_listing(self, session_id: str, updated_listing: dict[str, Any], user_id: str | None = None) -> dict[str, Any]:
        """사용자가 직접 수정한 판매글을 DB에 반영한다."""
        session = self._ensure_transition(session_id, "draft_generated", user_id)
        current_status = session["status"]

        listing_data = dict(session.get("listing_data_jsonb") or {})
        canonical = listing_data.get("canonical_listing") or {}

        # 사용자가 수정한 필드만 업데이트
        for key in ("title", "description", "price", "tags"):
            if key in updated_listing:
                canonical[key] = updated_listing[key]

        listing_data["canonical_listing"] = canonical

        return self._persist_and_respond(
            session_id, "draft_generated",
            expected_status=current_status,
            listing_data=listing_data,
        )

    # ── 게시 준비 / 게시 (PublishOrchestrator 위임) ──────────────────

    async def prepare_publish(self, session_id: str, platform_targets: list[str], user_id: str | None = None) -> dict[str, Any]:
        session = self._ensure_transition(session_id, "awaiting_publish_approval", user_id)
        return await self.publish_orchestrator.prepare_publish(
            session_id, session, session["status"], platform_targets,
        )

    async def publish_session(self, session_id: str, user_id: str | None = None) -> dict[str, Any]:
        session = self._ensure_transition(session_id, "publishing", user_id)
        return await self.publish_orchestrator.publish_session(
            session_id, session, session["status"], user_id=user_id,
        )

    # ── 판매 상태 입력 (SaleTracker 위임) ──────────────────────────

    async def update_sale_status(self, session_id: str, sale_status: str, user_id: str | None = None) -> dict[str, Any]:
        session = self._get_or_raise(session_id, user_id)
        return await self.sale_tracker.update_sale_status(session_id, session, sale_status)

    # ── 내부 헬퍼 ────────────────────────────────────────────────

    def _get_or_raise(self, session_id: str, user_id: str | None = None) -> dict[str, Any]:
        if user_id:
            # DB 레벨 소유권 검증: WHERE id=? AND user_id=?
            session = self.repo.get_by_id_and_user(session_id, user_id)
            if not session:
                raise SessionNotFoundError(f"세션을 찾을 수 없습니다: {session_id}")
        else:
            session = self.repo.get_by_id(session_id)
            if not session:
                raise SessionNotFoundError(f"세션을 찾을 수 없습니다: {session_id}")
        return session

    def _update_or_raise(
        self,
        session_id: str,
        payload: dict[str, Any],
        expected_status: str | None = None,
    ) -> dict[str, Any]:
        result = self.repo.update(
            session_id=session_id,
            payload=payload,
            expected_status=expected_status,
        )
        if not result:
            if expected_status:
                raise InvalidStateTransitionError(
                    f"세션 상태가 변경되었습니다 (expected={expected_status}): {session_id}"
                )
            raise SessionUpdateError(f"세션 업데이트 실패: {session_id}")
        return result

    def _ensure_transition(self, session_id: str, next_status: str, user_id: str | None = None) -> dict[str, Any]:
        """세션 조회 + 소유권 검증 + 상태 전이 유효성 검증을 한 번에 수행한다."""
        import logging
        logger = logging.getLogger(__name__)
        session = self._get_or_raise(session_id, user_id)
        from_status = session["status"]
        assert_allowed_transition(from_status, next_status)
        logger.info(
            "session_transition session_id=%s from=%s to=%s",
            session_id, from_status, next_status,
        )
        return session

    def _persist_and_respond(
        self,
        session_id: str,
        status: str,
        *,
        expected_status: str | None = None,
        product_data: dict[str, Any] | None = None,
        listing_data: dict[str, Any] | None = None,
        workflow_meta: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """상태 업데이트 + UI 응답 반환 공통 패턴."""
        payload: dict[str, Any] = {"status": status}
        if product_data is not None:
            payload["product_data_jsonb"] = product_data
        if listing_data is not None:
            payload["listing_data_jsonb"] = listing_data
        if workflow_meta is not None:
            payload["workflow_meta_jsonb"] = workflow_meta
        updated = self._update_or_raise(session_id, payload, expected_status)
        return build_session_ui_response(updated)
