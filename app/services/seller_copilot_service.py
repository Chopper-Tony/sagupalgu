from __future__ import annotations

from copy import deepcopy
from typing import Any

from app.domain.product_rules import (
    build_confirmed_product_from_candidate,
    build_confirmed_product_from_user_input,
    needs_user_input,
)
from app.graph.seller_copilot_runner import SellerCopilotRunner
from app.services.market.market_service import MarketService
from app.services.product_service import ProductService



class SellerCopilotService:
    """
    SessionService와 LangGraph 사이의 응용 서비스.

    Product/Market 분석은 각 서비스로 처리하고,
    확정된 입력(confirmed_product, market_context)을 LangGraph에 넘겨
    가격 전략 → 카피라이팅 → 검증 → 패키지 생성 구간을 실행한다.
    """

    def __init__(
        self,
        product_service: ProductService | None = None,
        market_service: MarketService | None = None,
        runner: SellerCopilotRunner | None = None,
    ):
        self.product_service = product_service or ProductService()
        self.market_service = market_service or MarketService()
        self.runner = runner or SellerCopilotRunner()

    # ── 내부 빌더 ─────────────────────────────────────────────────────

    def _build_confirmed_product_from_existing(
        self, existing_confirmed_product: dict[str, Any]
    ) -> dict[str, Any]:
        return {
            "brand": existing_confirmed_product.get("brand") or "",
            "model": existing_confirmed_product.get("model") or "",
            "category": existing_confirmed_product.get("category") or "",
            "confidence": float(
                existing_confirmed_product.get("confidence", 1.0) or 1.0
            ),
            "source": existing_confirmed_product.get("source", "session"),
            "storage": existing_confirmed_product.get("storage", "") or "",
        }

    def _build_product_payload(
        self,
        existing_product_data: dict[str, Any],
        *,
        image_paths: list[str],
        candidates: list[dict[str, Any]] | None = None,
        confirmed_product: dict[str, Any] | None = None,
        needs_user_input: bool = False,
        analysis_source: str = "vision",
    ) -> dict[str, Any]:
        product_data = deepcopy(existing_product_data)
        product_data["image_paths"] = image_paths
        product_data["image_count"] = len(image_paths)
        product_data["analysis_source"] = analysis_source

        if candidates is not None:
            product_data["candidates"] = candidates
        if confirmed_product is not None:
            product_data["confirmed_product"] = confirmed_product

        product_data["needs_user_input"] = needs_user_input
        if needs_user_input:
            product_data["user_input_type"] = "model_name"
            product_data["user_input_prompt"] = (
                "사진만으로 모델명을 정확히 식별하지 못했습니다. "
                "모델명을 직접 입력해 주세요. "
                "모델명이 잘 보이도록 다시 촬영한 사진을 올려도 됩니다."
            )
        else:
            product_data.pop("user_input_type", None)
            product_data.pop("user_input_prompt", None)

        return product_data

    def _build_listing_payload(
        self,
        existing_listing_data: dict[str, Any],
        final_state: dict[str, Any],
    ) -> dict[str, Any]:
        listing_data = deepcopy(existing_listing_data)
        for key in ("market_context", "strategy", "canonical_listing", "platform_packages"):
            if final_state.get(key) is not None:
                listing_data[key] = final_state[key]
        return listing_data

    def _build_workflow_payload(
        self,
        existing_workflow_meta: dict[str, Any],
        final_state: dict[str, Any],
        *,
        integration_phase: str,
    ) -> dict[str, Any]:
        workflow_meta = deepcopy(existing_workflow_meta)
        workflow_meta["schema_version"] = final_state.get(
            "schema_version", workflow_meta.get("schema_version", 1)
        )
        workflow_meta["checkpoint"] = final_state.get("checkpoint")
        workflow_meta["integration_phase"] = integration_phase
        workflow_meta["integration_path"] = "seller_copilot_service"
        workflow_meta["graph_debug_logs"] = final_state.get("debug_logs", [])
        workflow_meta["validation_result"] = final_state.get("validation_result")
        workflow_meta["last_error"] = final_state.get("last_error")
        # ── agent trace 보존 (CTO3 P0: tool_calls 소실 방지) ──
        workflow_meta["tool_calls"] = final_state.get("tool_calls", [])
        workflow_meta["decision_rationale"] = final_state.get("decision_rationale", [])
        workflow_meta["plan"] = final_state.get("plan")
        workflow_meta["critic_score"] = final_state.get("critic_score")
        workflow_meta["critic_feedback"] = final_state.get("critic_feedback", [])
        workflow_meta["execution_metrics"] = final_state.get("execution_metrics", [])
        return workflow_meta

    def _run_graph(
        self,
        *,
        session_id: str,
        image_paths: list[str],
        selected_platforms: list[str],
        confirmed_product: dict[str, Any],
        market_context: dict[str, Any],
        rewrite_instruction: str | None = None,
    ) -> dict[str, Any]:
        common = dict(
            session_id=session_id,
            image_paths=image_paths,
            selected_platforms=selected_platforms,
            market_context=market_context,
            rewrite_instruction=rewrite_instruction,
        )
        if confirmed_product.get("source") == "user_input":
            common["user_product_input"] = {
                "brand": confirmed_product.get("brand"),
                "model": confirmed_product.get("model"),
                "category": confirmed_product.get("category"),
                "storage": confirmed_product.get("storage", ""),
            }
        else:
            common["product_candidates"] = [confirmed_product]

        state = self.runner.build_initial_state(**common)
        # 상품이 이미 확정되고 시세 데이터도 준비된 상태이므로
        # pre-listing 질문 단계를 건너뛴다.
        state["pre_listing_done"] = True

        from app.graph.seller_copilot_graph import seller_copilot_graph
        return seller_copilot_graph.invoke(state)

    # ── 공개 API ──────────────────────────────────────────────────────

    async def _resolve_product(
        self,
        product_data: dict[str, Any],
        image_paths: list[str],
        user_product_input: dict[str, Any] | None,
    ) -> tuple[dict[str, Any], dict[str, Any], str]:
        """상품 확정 3-way 분기. (confirmed_product, product_data, analysis_source)를 반환.

        사용자 입력이 이미 없으면 Vision 재분석.
        needs_user_input이면 None을 반환하여 호출자가 조기 반환하도록 한다.
        """
        existing = product_data.get("confirmed_product")
        analysis_source = product_data.get("analysis_source", "vision")

        # 1) 이미 세션에 confirmed_product가 있으면 최우선 사용
        if existing:
            confirmed = self._build_confirmed_product_from_existing(existing)
            product_data = self._build_product_payload(
                product_data, image_paths=image_paths,
                candidates=product_data.get("candidates", []),
                confirmed_product=confirmed, needs_user_input=False,
                analysis_source=confirmed.get("source", analysis_source),
            )
            return confirmed, product_data, confirmed.get("source", analysis_source)

        # 2) 이번 요청에서 새로 user input이 들어오면 그걸 사용
        if user_product_input:
            confirmed = build_confirmed_product_from_user_input(
                model=user_product_input.get("model", ""),
                brand=user_product_input.get("brand"),
                category=user_product_input.get("category"),
            )
            product_data = self._build_product_payload(
                product_data, image_paths=image_paths,
                candidates=product_data.get("candidates", []),
                confirmed_product=confirmed, needs_user_input=False,
                analysis_source="user_input",
            )
            return confirmed, product_data, "user_input"

        # 3) vision 재분석
        try:
            vision_result = await self.product_service.identify_product(image_paths)
        except Exception as exc:
            raise ValueError(f"Vision analysis failed: {exc}") from exc

        candidates = list(getattr(vision_result, "candidates", []) or [])
        if not candidates:
            raise ValueError("Vision provider returned no candidates")

        top = candidates[0]
        if needs_user_input(top):
            # needs_user_input → None 반환으로 조기 반환 시그널
            product_data = self._build_product_payload(
                product_data, image_paths=image_paths,
                candidates=candidates, confirmed_product=None,
                needs_user_input=True, analysis_source="vision",
            )
            return None, product_data, "vision"  # type: ignore[return-value]

        confirmed = build_confirmed_product_from_candidate(top)
        product_data = self._build_product_payload(
            product_data, image_paths=image_paths,
            candidates=candidates, confirmed_product=confirmed,
            needs_user_input=False, analysis_source="vision",
        )
        return confirmed, product_data, "vision"

    async def _run_market_and_graph(
        self,
        *,
        session_id: str,
        image_paths: list[str],
        target_platforms: list[str],
        confirmed_product: dict[str, Any],
        market_context: dict[str, Any] | None = None,
        rewrite_instruction: str | None = None,
    ) -> dict[str, Any]:
        """시세 분석 + LangGraph 실행."""
        if market_context is None:
            try:
                market_context = await self.market_service.analyze_market(confirmed_product)
            except Exception as exc:
                raise ValueError(f"Market analysis failed: {exc}") from exc

        return self._run_graph(
            session_id=session_id, image_paths=image_paths,
            selected_platforms=target_platforms,
            confirmed_product=confirmed_product,
            market_context=market_context,
            rewrite_instruction=rewrite_instruction,
        )

    def _assemble_result(
        self,
        *,
        session_id: str,
        product_data: dict[str, Any],
        listing_data: dict[str, Any],
        workflow_meta: dict[str, Any],
        target_platforms: list[str],
        final_state: dict[str, Any],
        confirmed_product: dict[str, Any],
        analysis_source: str,
    ) -> dict[str, Any]:
        """그래프 실행 결과를 세션 payload로 조립."""
        if final_state.get("confirmed_product"):
            product_data["confirmed_product"] = final_state["confirmed_product"]

        product_data["needs_user_input"] = False
        product_data.pop("user_input_type", None)
        product_data.pop("user_input_prompt", None)
        product_data["analysis_source"] = confirmed_product.get("source", analysis_source)

        return {
            "session_id": session_id,
            "status": final_state.get("status", "draft_generated"),
            "selected_platforms_jsonb": target_platforms,
            "product_data_jsonb": product_data,
            "listing_data_jsonb": self._build_listing_payload(listing_data, final_state),
            "workflow_meta_jsonb": self._build_workflow_payload(
                workflow_meta, final_state, integration_phase="seller_copilot_service",
            ),
        }

    async def run_product_analysis_and_listing_pipeline(
        self,
        *,
        session_id: str,
        session_record: dict[str, Any],
        selected_platforms: list[str] | None = None,
        user_product_input: dict[str, Any] | None = None,
        rewrite_instruction: str | None = None,
    ) -> dict[str, Any]:
        product_data = deepcopy(session_record.get("product_data_jsonb") or {})
        listing_data = deepcopy(session_record.get("listing_data_jsonb") or {})
        workflow_meta = deepcopy(session_record.get("workflow_meta_jsonb") or {})

        image_paths = product_data.get("image_paths", [])
        if not image_paths:
            raise ValueError(f"No images found for session: {session_id}")

        target_platforms = (
            selected_platforms
            or session_record.get("selected_platforms_jsonb")
            or ["bunjang", "joongna"]
        )

        confirmed_product, product_data, analysis_source = await self._resolve_product(
            product_data, image_paths, user_product_input,
        )

        # needs_user_input → 조기 반환
        if confirmed_product is None:
            workflow_meta["checkpoint"] = "A_needs_user_input"
            workflow_meta["integration_phase"] = "seller_copilot_service"
            workflow_meta["integration_path"] = "seller_copilot_service"
            return {
                "session_id": session_id,
                "status": "awaiting_product_confirmation",
                "selected_platforms_jsonb": target_platforms,
                "product_data_jsonb": product_data,
                "listing_data_jsonb": listing_data,
                "workflow_meta_jsonb": workflow_meta,
            }

        final_state = await self._run_market_and_graph(
            session_id=session_id, image_paths=image_paths,
            target_platforms=target_platforms,
            confirmed_product=confirmed_product,
            rewrite_instruction=rewrite_instruction,
        )

        return self._assemble_result(
            session_id=session_id, product_data=product_data,
            listing_data=listing_data, workflow_meta=workflow_meta,
            target_platforms=target_platforms, final_state=final_state,
            confirmed_product=confirmed_product, analysis_source=analysis_source,
        )

    async def run_listing_pipeline(
        self, session_id: str, session_record: dict[str, Any]
    ) -> dict[str, Any]:
        return await self.run_product_analysis_and_listing_pipeline(
            session_id=session_id,
            session_record=session_record,
        )

    async def run_rewrite_pipeline(
        self,
        session_id: str,
        session_record: dict[str, Any],
        rewrite_instruction: str,
    ) -> dict[str, Any]:
        return await self.run_product_analysis_and_listing_pipeline(
            session_id=session_id,
            session_record=session_record,
            rewrite_instruction=rewrite_instruction,
        )
