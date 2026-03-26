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

        candidates: list[dict[str, Any]] = []
        existing_confirmed_product = product_data.get("confirmed_product")
        analysis_source = product_data.get("analysis_source", "vision")

        # 1) 이미 세션에 confirmed_product가 있으면 최우선 사용
        if existing_confirmed_product:
            confirmed_product = self._build_confirmed_product_from_existing(existing_confirmed_product)
            product_data = self._build_product_payload(
                product_data,
                image_paths=image_paths,
                candidates=product_data.get("candidates", []),
                confirmed_product=confirmed_product,
                needs_user_input=False,
                analysis_source=confirmed_product.get("source", analysis_source),
            )

        # 2) 이번 요청에서 새로 user input이 들어오면 그걸 사용
        elif user_product_input:
            confirmed_product = build_confirmed_product_from_user_input(
                model=user_product_input.get("model", ""),
                brand=user_product_input.get("brand"),
                category=user_product_input.get("category"),
            )
            analysis_source = "user_input"
            product_data = self._build_product_payload(
                product_data,
                image_paths=image_paths,
                candidates=product_data.get("candidates", []),
                confirmed_product=confirmed_product,
                needs_user_input=False,
                analysis_source=analysis_source,
            )

        # 3) confirmed_product가 없을 때만 vision 재분석
        else:
            try:
                vision_result = await self.product_service.identify_product(image_paths)
            except Exception as exc:
                raise ValueError(f"Vision analysis failed: {exc}") from exc

            candidates = list(getattr(vision_result, "candidates", []) or [])
            if not candidates:
                raise ValueError("Vision provider returned no candidates")

            top_candidate = candidates[0]
            if needs_user_input(top_candidate):
                product_data = self._build_product_payload(
                    product_data,
                    image_paths=image_paths,
                    candidates=candidates,
                    confirmed_product=None,
                    needs_user_input=True,
                    analysis_source="vision",
                )
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

            confirmed_product = build_confirmed_product_from_candidate(top_candidate)
            analysis_source = "vision"
            product_data = self._build_product_payload(
                product_data,
                image_paths=image_paths,
                candidates=candidates,
                confirmed_product=confirmed_product,
                needs_user_input=False,
                analysis_source=analysis_source,
            )

        try:
            market_context = await self.market_service.analyze_market(confirmed_product)
        except Exception as exc:
            raise ValueError(f"Market analysis failed: {exc}") from exc

        final_state = self._run_graph(
            session_id=session_id,
            image_paths=image_paths,
            selected_platforms=target_platforms,
            confirmed_product=confirmed_product,
            market_context=market_context,
            rewrite_instruction=rewrite_instruction,
        )

        if final_state.get("confirmed_product"):
            product_data["confirmed_product"] = final_state["confirmed_product"]

        product_data["needs_user_input"] = False
        product_data.pop("user_input_type", None)
        product_data.pop("user_input_prompt", None)
        product_data["analysis_source"] = confirmed_product.get("source", analysis_source)

        listing_data = self._build_listing_payload(listing_data, final_state)
        workflow_meta = self._build_workflow_payload(
            workflow_meta, final_state, integration_phase="seller_copilot_service"
        )

        return {
            "session_id": session_id,
            "status": final_state.get("status", "draft_generated"),
            "selected_platforms_jsonb": target_platforms,
            "product_data_jsonb": product_data,
            "listing_data_jsonb": listing_data,
            "workflow_meta_jsonb": workflow_meta,
        }

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
