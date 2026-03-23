"""
SessionService — 에이전틱 버전.

변경 사항:
1. 전체 async 전환 (asyncio.run() 제거)
2. publish 실패 시 recovery_node 직접 호출
3. sale-status 입력 시 post_sale_optimization_node 직접 호출
4. rewrite-listing 지원
5. (M2) _resolve_next_action → app.domain.session_status.resolve_next_action 단일화
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.domain.session_status import resolve_next_action
from app.repositories.session_repository import SessionRepository
from app.services.product_service import ProductService
from app.services.publish_service import PublishService
from app.services.seller_copilot_service import (
    SellerCopilotService,
    _needs_user_input,
    _normalize_text,
)


class SessionService:
    def __init__(self, session_repository: SessionRepository):
        self.repo = session_repository
        self.product_service = ProductService()
        self.publish_service = PublishService()
        self.copilot_service = SellerCopilotService()

    # ── 세션 생성 / 조회 ───────────────────────────────────────────

    async def create_session(self, user_id: str) -> Dict:
        session = self.repo.create(user_id=user_id)
        return {"session_id": session.id, "status": session.status}

    async def get_session(self, session_id: str) -> Dict:
        session = self._get_or_raise(session_id)
        return {
            "session_id": session["id"],
            "status": session["status"],
            "product_data_jsonb": session.get("product_data_jsonb") or {},
            "listing_data_jsonb": session.get("listing_data_jsonb") or {},
            "workflow_meta_jsonb": session.get("workflow_meta_jsonb") or {},
        }

    # ── 이미지 업로드 ──────────────────────────────────────────────

    async def attach_images(self, session_id: str, image_urls: List[str]) -> Dict:
        session = self._get_or_raise(session_id)
        product_data = dict(session.get("product_data_jsonb") or {})
        product_data["image_paths"] = image_urls
        updated = self._update_or_raise(session_id, {
            "status": "images_uploaded",
            "product_data_jsonb": product_data,
        })
        return self._ui_response(updated)

    # ── 상품 분석 ──────────────────────────────────────────────────

    async def analyze_session(self, session_id: str) -> Dict:
        session = self._get_or_raise(session_id)
        self._assert_status(session, "images_uploaded")

        product_data = dict(session.get("product_data_jsonb") or {})
        image_paths = product_data.get("image_paths") or []
        if not image_paths:
            raise ValueError("이미지가 없습니다")

        result = await self.product_service.identify_product(image_paths)
        candidates = result.candidates or []

        if not candidates:
            raise ValueError("상품 인식 결과가 없습니다")

        top = candidates[0]
        needs_input = _needs_user_input(top)

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
        workflow_meta["checkpoint"] = "A_needs_user_input" if needs_input else "A_before_confirm"

        updated = self._update_or_raise(session_id, {
            "status": "awaiting_product_confirmation",
            "product_data_jsonb": product_data,
            "workflow_meta_jsonb": workflow_meta,
        })
        return self._ui_response(updated)

    # ── 상품 확정 ──────────────────────────────────────────────────

    async def confirm_product(self, session_id: str, candidate_index: int) -> Dict:
        session = self._get_or_raise(session_id)
        self._assert_status(session, "awaiting_product_confirmation")

        product_data = dict(session.get("product_data_jsonb") or {})
        candidates = product_data.get("candidates") or []

        if not (0 <= candidate_index < len(candidates)):
            raise ValueError("유효하지 않은 후보 인덱스입니다")

        confirmed = {**candidates[candidate_index], "source": "vision"}
        product_data["confirmed_product"] = confirmed
        product_data["needs_user_input"] = False
        product_data.pop("user_input_prompt", None)

        workflow_meta = dict(session.get("workflow_meta_jsonb") or {})
        workflow_meta["checkpoint"] = "A_complete"

        updated = self._update_or_raise(session_id, {
            "status": "product_confirmed",
            "product_data_jsonb": product_data,
            "workflow_meta_jsonb": workflow_meta,
        })
        return self._ui_response(updated)

    async def provide_product_info(
        self, session_id: str, model: str,
        brand: Optional[str] = None, category: Optional[str] = None,
    ) -> Dict:
        session = self._get_or_raise(session_id)
        self._assert_status(session, "awaiting_product_confirmation")

        normalized_model = _normalize_text(model)
        if not normalized_model:
            raise ValueError("모델명은 필수입니다")

        product_data = dict(session.get("product_data_jsonb") or {})
        product_data["confirmed_product"] = {
            "brand": _normalize_text(brand) or "Unknown",
            "model": normalized_model,
            "category": _normalize_text(category) or "unknown",
            "confidence": 1.0,
            "source": "user_input",
        }
        product_data["needs_user_input"] = False
        product_data.pop("user_input_prompt", None)

        workflow_meta = dict(session.get("workflow_meta_jsonb") or {})
        workflow_meta["checkpoint"] = "A_complete"

        updated = self._update_or_raise(session_id, {
            "status": "product_confirmed",
            "product_data_jsonb": product_data,
            "workflow_meta_jsonb": workflow_meta,
        })
        return self._ui_response(updated)

    # ── 판매글 생성 ────────────────────────────────────────────────

    async def generate_listing(self, session_id: str) -> Dict:
        session = self._get_or_raise(session_id)
        self._assert_status(session, "product_confirmed")

        # LangGraph 기반 파이프라인 실행 (에이전트 2, 3, 4)
        result_payload = await self.copilot_service.run_listing_pipeline(
            session_id=session_id,
            session_record=session,
        )

        listing_data = dict(result_payload.get("listing_data_jsonb") or {})
        listing_data.pop("platform_packages", None)

        workflow_meta = dict(result_payload.get("workflow_meta_jsonb") or {})
        if workflow_meta.get("checkpoint") in {"C_prepared", "C_complete"}:
            workflow_meta["checkpoint"] = "B_complete"
        workflow_meta.pop("publish_results", None)

        # tool_calls 기록도 저장
        workflow_meta["tool_calls"] = result_payload.get("tool_calls") or []

        updated = self._update_or_raise(session_id, {
            "status": "draft_generated",
            "selected_platforms_jsonb": [],
            "product_data_jsonb": result_payload.get("product_data_jsonb") or {},
            "listing_data_jsonb": listing_data,
            "workflow_meta_jsonb": workflow_meta,
        })
        return self._ui_response(updated)

    # ── 판매글 재작성 (신규 API) ───────────────────────────────────

    async def rewrite_listing(self, session_id: str, instruction: str) -> Dict:
        """
        사용자 피드백 기반 재작성.
        에이전트 3의 rewrite_listing_tool을 트리거.
        """
        session = self._get_or_raise(session_id)
        self._assert_status(session, "draft_generated")

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
        rewrite_history = workflow_meta.get("rewrite_history") or []
        rewrite_history.append({
            "instruction": instruction,
            "timestamp": __import__("datetime").datetime.utcnow().isoformat(),
        })
        workflow_meta["rewrite_history"] = rewrite_history
        workflow_meta["tool_calls"] = result_payload.get("tool_calls") or []

        updated = self._update_or_raise(session_id, {
            "status": "draft_generated",
            "listing_data_jsonb": listing_data,
            "workflow_meta_jsonb": workflow_meta,
        })
        return self._ui_response(updated)

    # ── 게시 준비 / 게시 ───────────────────────────────────────────

    async def prepare_publish(self, session_id: str, platform_targets: List[str]) -> Dict:
        session = self._get_or_raise(session_id)
        self._assert_status(session, "draft_generated")

        if not platform_targets:
            raise ValueError("플랫폼을 선택해주세요")

        listing_data = dict(session.get("listing_data_jsonb") or {})
        canonical = listing_data.get("canonical_listing") or {}
        market_context = listing_data.get("market_context") or {}

        if _safe_int(canonical.get("price"), 0) <= 0:
            raise ValueError("유효한 가격이 없습니다. 판매글을 다시 생성해주세요.")

        canonical_price = int(canonical.get("price", 0))
        platform_packages: Dict[str, Any] = {}

        for platform in platform_targets:
            if platform == "bunjang":
                p_price = canonical_price + 10000
            elif platform == "daangn":
                p_price = max(canonical_price - 4000, 0)
            else:
                p_price = canonical_price

            platform_packages[platform] = {
                "title": canonical.get("title", ""),
                "body": canonical.get("description", ""),
                "price": p_price,
                "images": canonical.get("images", []),
            }

        listing_data["platform_packages"] = platform_packages
        workflow_meta = dict(session.get("workflow_meta_jsonb") or {})
        workflow_meta["checkpoint"] = "C_prepared"
        workflow_meta.pop("publish_results", None)

        updated = self._update_or_raise(session_id, {
            "status": "awaiting_publish_approval",
            "selected_platforms_jsonb": platform_targets,
            "listing_data_jsonb": listing_data,
            "workflow_meta_jsonb": workflow_meta,
        })
        return self._ui_response(updated)

    async def publish_session(self, session_id: str) -> Dict:
        session = self._get_or_raise(session_id)
        self._assert_status(session, "awaiting_publish_approval")

        selected = session.get("selected_platforms_jsonb") or []
        listing_data = dict(session.get("listing_data_jsonb") or {})
        packages = listing_data.get("platform_packages") or {}

        if not selected:
            raise ValueError("선택된 플랫폼이 없습니다")

        workflow_meta = dict(session.get("workflow_meta_jsonb") or {})
        self._update_or_raise(session_id, {
            "status": "publishing",
            "workflow_meta_jsonb": workflow_meta,
        })

        publish_results: Dict[str, Any] = {}
        any_failure = False

        for platform in selected:
            payload = packages.get(platform)
            if not payload:
                publish_results[platform] = {
                    "success": False,
                    "platform": platform,
                    "error_code": "missing_platform_package",
                    "error_message": f"{platform} 패키지 없음",
                }
                any_failure = True
                continue

            try:
                result = await self.publish_service.publish(platform=platform, payload=payload)
                publish_results[platform] = {
                    "success": result.success,
                    "platform": result.platform,
                    "external_listing_id": result.external_listing_id,
                    "external_url": result.external_url,
                    "error_code": result.error_code,
                    "error_message": result.error_message,
                    "evidence_path": result.evidence_path,
                }
                if not result.success:
                    any_failure = True
            except Exception as e:
                publish_results[platform] = {
                    "success": False,
                    "platform": platform,
                    "error_code": "publish_exception",
                    "error_message": str(e),
                }
                any_failure = True

        workflow_meta["checkpoint"] = "C_complete"
        workflow_meta["publish_results"] = publish_results

        if any_failure:
            # ── 에이전트 4 복구 노드 직접 호출 ────────────────────
            from app.graph.seller_copilot_nodes import recovery_node
            updated_session = self.repo.get_by_id(session_id)
            recovery_state = self._build_recovery_state(
                session_id=session_id,
                session=updated_session,
                publish_results=publish_results,
            )
            final_state = recovery_node(recovery_state)
            workflow_meta["publish_diagnostics"] = final_state.get("publish_diagnostics") or []
            workflow_meta["tool_calls"] = (
                (workflow_meta.get("tool_calls") or [])
                + (final_state.get("tool_calls") or [])
            )
            final_status = "publishing_failed"
        else:
            final_status = "completed"

        updated = self._update_or_raise(session_id, {
            "status": final_status,
            "workflow_meta_jsonb": workflow_meta,
        })
        return self._ui_response(updated)

    # ── 판매 상태 입력 (신규 API) ─────────────────────────────────

    async def update_sale_status(self, session_id: str, sale_status: str) -> Dict:
        """
        사용자가 "팔렸어요" / "아직이에요" 입력.
        에이전트 5를 트리거.
        """
        if sale_status not in ("sold", "unsold", "in_progress"):
            raise ValueError("sale_status는 sold / unsold / in_progress 중 하나여야 합니다")

        session = self._get_or_raise(session_id)

        workflow_meta = dict(session.get("workflow_meta_jsonb") or {})
        workflow_meta["sale_status"] = sale_status

        # 에이전트 5: 판매 후 최적화 노드 직접 호출
        from app.graph.seller_copilot_nodes import post_sale_optimization_node
        from app.graph.seller_copilot_state import create_initial_state

        listing_data = session.get("listing_data_jsonb") or {}
        product_data = session.get("product_data_jsonb") or {}

        opt_state = create_initial_state(
            session_id=session_id,
            image_paths=product_data.get("image_paths") or [],
        )
        opt_state["sale_status"] = sale_status
        opt_state["canonical_listing"] = listing_data.get("canonical_listing")
        opt_state["confirmed_product"] = product_data.get("confirmed_product")
        opt_state["followup_due_at"] = workflow_meta.get("followup_due_at")

        final_state = post_sale_optimization_node(opt_state)

        optimization = final_state.get("optimization_suggestion")
        if optimization:
            listing_data["optimization_suggestion"] = optimization

        workflow_meta["tool_calls"] = (
            (workflow_meta.get("tool_calls") or [])
            + (final_state.get("tool_calls") or [])
        )

        final_status = final_state.get("status") or (
            "optimization_suggested" if optimization else "awaiting_sale_status_update"
        )

        updated = self._update_or_raise(session_id, {
            "status": final_status,
            "listing_data_jsonb": listing_data,
            "workflow_meta_jsonb": workflow_meta,
        })
        return self._ui_response(updated)

    # ── 내부 헬퍼 ────────────────────────────────────────────────

    def _get_or_raise(self, session_id: str) -> Dict:
        session = self.repo.get_by_id(session_id)
        if not session:
            raise ValueError(f"세션을 찾을 수 없습니다: {session_id}")
        return session

    def _update_or_raise(self, session_id: str, payload: Dict) -> Dict:
        result = self.repo.update(session_id=session_id, payload=payload)
        if not result:
            raise ValueError(f"세션 업데이트 실패: {session_id}")
        return result

    def _assert_status(self, session: Dict, expected: str) -> None:
        current = session.get("status")
        if current != expected:
            raise ValueError(
                f"현재 상태 '{current}'에서는 이 작업을 수행할 수 없습니다 (필요 상태: '{expected}')"
            )

    def _build_recovery_state(
        self, session_id: str, session: Dict, publish_results: Dict
    ) -> Dict:
        from app.graph.seller_copilot_state import create_initial_state
        product_data = session.get("product_data_jsonb") or {}
        state = create_initial_state(
            session_id=session_id,
            image_paths=product_data.get("image_paths") or [],
        )
        state["publish_results"] = publish_results
        state["confirmed_product"] = product_data.get("confirmed_product")
        return state

    def _ui_response(self, session: Dict) -> Dict:
        """모든 엔드포인트가 동일한 평탄화된 구조를 반환"""
        product_data = session.get("product_data_jsonb") or {}
        listing_data = session.get("listing_data_jsonb") or {}
        workflow_meta = session.get("workflow_meta_jsonb") or {}
        status = session.get("status", "")
        needs_input = bool(product_data.get("needs_user_input", False))

        return {
            "session_id": session.get("id") or session.get("session_id"),
            "status": status,
            "checkpoint": workflow_meta.get("checkpoint"),
            "next_action": resolve_next_action(status, needs_input),
            "needs_user_input": needs_input,
            "user_input_prompt": product_data.get("user_input_prompt"),
            "selected_platforms": session.get("selected_platforms_jsonb") or [],
            "product": {
                "image_paths": product_data.get("image_paths") or [],
                "candidates": product_data.get("candidates") or [],
                "confirmed_product": product_data.get("confirmed_product"),
                "analysis_source": product_data.get("analysis_source"),
            },
            "listing": {
                "market_context": listing_data.get("market_context"),
                "strategy": listing_data.get("strategy"),
                "canonical_listing": listing_data.get("canonical_listing"),
                "platform_packages": listing_data.get("platform_packages") or {},
                "optimization_suggestion": listing_data.get("optimization_suggestion"),
            },
            "publish": {
                "results": workflow_meta.get("publish_results") or {},
                "diagnostics": workflow_meta.get("publish_diagnostics") or [],
            },
            "agent_trace": {
                "tool_calls": workflow_meta.get("tool_calls") or [],
                "rewrite_history": workflow_meta.get("rewrite_history") or [],
            },
            "debug": {
                "last_error": workflow_meta.get("last_error"),
            },
        }


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
