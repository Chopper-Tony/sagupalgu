from __future__ import annotations

import asyncio
from copy import deepcopy
from typing import Any

from app.graph.seller_copilot_runner import SellerCopilotRunner
from app.services.market.market_service import MarketService
from app.services.product_service import ProductService


class SellerCopilotService:
    """
    SessionService와 LangGraph 사이의 응용 서비스.

    현재 코드베이스 기준에서는 Product/Market 단계는 기존 서비스로 확정하고,
    LangGraph에는 확정된 입력(product_candidates or user_product_input, market_context)
    을 넣어 B/C 구간(가격 전략, 카피라이팅, 검증, 패키지 생성)을 안정적으로 실행한다.

    이유:
    - 현재 SellerCopilotRunner는 hook 결과를 graph 실행 전에 eager precompute 한다.
    - 그래서 confirmed_product가 생기기 전에는 market/copy hook가 제대로 동작할 수 없다.
    - 지금 단계에서는 '작동하는 production path'를 먼저 만들고,
      다음 단계에서 hook lazy execution으로 고도화하는 편이 맞다.
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

    def _normalize_text(self, value: str | None) -> str:
        if not value:
            return ""

        value = str(value).strip()
        if value.lower() in {"unknown", "none", "null", "n/a"}:
            return ""

        return value

    def _needs_user_input(self, candidate: dict[str, Any]) -> bool:
        brand = self._normalize_text(candidate.get("brand"))
        model = self._normalize_text(candidate.get("model"))
        category = self._normalize_text(candidate.get("category"))
        confidence = float(candidate.get("confidence", 0.0) or 0.0)

        if not model:
            return True
        if not brand and not category:
            return True
        if confidence < 0.6:
            return True

        return False

    def _build_clarification_prompt(self) -> str:
        return (
            "사진만으로 모델명을 정확히 식별하지 못했습니다. "
            "모델명을 직접 입력해 주세요. "
            "모델명이 잘 보이도록 다시 촬영한 사진을 올려도 됩니다."
        )

    def _build_confirmed_product_from_candidate(
        self, candidate: dict[str, Any]
    ) -> dict[str, Any]:
        return {
            "brand": candidate.get("brand") or "",
            "model": candidate.get("model") or "",
            "category": candidate.get("category") or "",
            "confidence": float(candidate.get("confidence", 0.0) or 0.0),
            "source": candidate.get("source", "vision"),
            "storage": candidate.get("storage", "") or "",
        }

    def _build_confirmed_product_from_user_input(
        self,
        model: str,
        brand: str | None = None,
        category: str | None = None,
    ) -> dict[str, Any]:
        normalized_model = self._normalize_text(model)
        normalized_brand = self._normalize_text(brand)
        normalized_category = self._normalize_text(category)

        if not normalized_model:
            raise ValueError("Model name is required")

        return {
            "brand": normalized_brand or "Unknown",
            "model": normalized_model,
            "category": normalized_category or "unknown",
            "confidence": 1.0,
            "source": "user_input",
            "storage": "",
        }

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
            product_data["user_input_prompt"] = self._build_clarification_prompt()
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

        if final_state.get("market_context") is not None:
            listing_data["market_context"] = final_state.get("market_context")
        if final_state.get("strategy") is not None:
            listing_data["strategy"] = final_state.get("strategy")
        if final_state.get("canonical_listing") is not None:
            listing_data["canonical_listing"] = final_state.get("canonical_listing")
        if final_state.get("platform_packages") is not None:
            listing_data["platform_packages"] = final_state.get("platform_packages")

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
            "schema_version",
            workflow_meta.get("schema_version", 1),
        )
        workflow_meta["checkpoint"] = final_state.get("checkpoint")
        workflow_meta["integration_phase"] = integration_phase
        workflow_meta["integration_path"] = "seller_copilot_service"
        workflow_meta["graph_debug_logs"] = final_state.get("debug_logs", [])
        workflow_meta["validation_result"] = final_state.get("validation_result")
        workflow_meta["last_error"] = final_state.get("last_error")

        return workflow_meta

    def _run_graph_for_confirmed_product(
        self,
        *,
        session_id: str,
        image_paths: list[str],
        selected_platforms: list[str],
        confirmed_product: dict[str, Any],
        market_context: dict[str, Any],
    ) -> dict[str, Any]:
        if confirmed_product.get("source") == "user_input":
            return self.runner.run(
                session_id=session_id,
                image_paths=image_paths,
                selected_platforms=selected_platforms,
                user_product_input={
                    "brand": confirmed_product.get("brand"),
                    "model": confirmed_product.get("model"),
                    "category": confirmed_product.get("category"),
                    "storage": confirmed_product.get("storage", ""),
                },
                market_context=market_context,
            )

        return self.runner.run(
            session_id=session_id,
            image_paths=image_paths,
            selected_platforms=selected_platforms,
            product_candidates=[confirmed_product],
            market_context=market_context,
        )

    def run_product_analysis_and_listing_pipeline(
        self,
        *,
        session_id: str,
        session_record: dict[str, Any],
        selected_platforms: list[str] | None = None,
        user_product_input: dict[str, Any] | None = None,
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
            confirmed_product = self._build_confirmed_product_from_existing(
                existing_confirmed_product
            )

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
            confirmed_product = self._build_confirmed_product_from_user_input(
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
                vision_result = asyncio.run(
                    self.product_service.identify_product(image_paths)
                )
            except Exception as exc:
                raise ValueError(f"Vision analysis failed: {exc}") from exc

            candidates = list(getattr(vision_result, "candidates", []) or [])
            if not candidates:
                raise ValueError("Vision provider returned no candidates")

            top_candidate = candidates[0]
            if self._needs_user_input(top_candidate):
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

            confirmed_product = self._build_confirmed_product_from_candidate(
                top_candidate
            )
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
            market_context = asyncio.run(
                self.market_service.analyze_market(confirmed_product)
            )
        except Exception as exc:
            raise ValueError(f"Market analysis failed: {exc}") from exc

        final_state = self._run_graph_for_confirmed_product(
            session_id=session_id,
            image_paths=image_paths,
            selected_platforms=target_platforms,
            confirmed_product=confirmed_product,
            market_context=market_context,
        )

        if final_state.get("confirmed_product"):
            product_data["confirmed_product"] = final_state["confirmed_product"]

        product_data["needs_user_input"] = False
        product_data.pop("user_input_type", None)
        product_data.pop("user_input_prompt", None)
        product_data["analysis_source"] = confirmed_product.get("source", analysis_source)

        listing_data = self._build_listing_payload(listing_data, final_state)
        workflow_meta = self._build_workflow_payload(
            workflow_meta,
            final_state,
            integration_phase="seller_copilot_service",
        )

        return {
            "session_id": session_id,
            "status": final_state.get("status", "draft_generated"),
            "selected_platforms_jsonb": target_platforms,
            "product_data_jsonb": product_data,
            "listing_data_jsonb": listing_data,
            "workflow_meta_jsonb": workflow_meta,
        }