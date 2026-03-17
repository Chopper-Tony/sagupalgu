import asyncio

from app.repositories.session_repository import SessionRepository
from app.services.product_service import ProductService
from app.services.publish_service import PublishService
from app.services.seller_copilot_service import SellerCopilotService


class SessionService:
    def __init__(self, session_repository: SessionRepository):
        self.session_repository = session_repository
        self.product_service = ProductService()
        self.publish_service = PublishService()
        self.seller_copilot_service = SellerCopilotService()

    def _normalize_text(self, value: str | None) -> str:
        if not value:
            return ""

        value = str(value).strip()

        if value.lower() in {"unknown", "none", "null", "n/a"}:
            return ""

        return value

    def _needs_user_input(self, candidate: dict) -> bool:
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

    def create_session(self, user_id: str):
        session = self.session_repository.create(user_id=user_id)
        return {
            "session_id": session.id,
            "status": session.status,
        }

    def get_session(self, session_id: str):
        session = self.session_repository.get_by_id(session_id)

        if not session:
            raise ValueError(f"Session not found: {session_id}")

        return {
            "session_id": session["id"],
            "status": session["status"],
            "product_data_jsonb": session.get("product_data_jsonb", {}),
            "listing_data_jsonb": session.get("listing_data_jsonb", {}),
            "workflow_meta_jsonb": session.get("workflow_meta_jsonb", {}),
        }

    def attach_images(self, session_id: str, image_urls: list[str]):
        session = self.session_repository.get_by_id(session_id)

        if not session:
            raise ValueError(f"Session not found: {session_id}")

        product_data = session.get("product_data_jsonb", {}) or {}
        product_data["image_paths"] = image_urls

        updated = self.session_repository.update(
            session_id=session_id,
            payload={
                "status": "images_uploaded",
                "product_data_jsonb": product_data,
            },
        )

        if not updated:
            raise ValueError(f"Failed to update session: {session_id}")

        return {
            "session_id": updated["id"],
            "status": updated["status"],
            "product_data_jsonb": updated.get("product_data_jsonb", {}),
        }

    def analyze_session(self, session_id: str):
        session = self.session_repository.get_by_id(session_id)

        if not session:
            raise ValueError(f"Session not found: {session_id}")

        if session.get("status") != "images_uploaded":
            raise ValueError(
                f"Session is not ready for analysis: {session_id} "
                f"(current status: {session.get('status')})"
            )

        product_data = session.get("product_data_jsonb", {}) or {}
        image_paths = product_data.get("image_paths", [])

        if not image_paths:
            raise ValueError(f"No images found for session: {session_id}")

        try:
            result = asyncio.run(self.product_service.identify_product(image_paths))
        except Exception as e:
            raise ValueError(f"Vision analysis failed: {str(e)}")

        candidates = result.candidates

        if not candidates:
            raise ValueError("Vision provider returned no candidates")

        top_candidate = candidates[0]
        needs_user_input = self._needs_user_input(top_candidate)

        product_data["candidates"] = candidates
        product_data["analysis_source"] = "vision"
        product_data["image_count"] = len(image_paths)

        if needs_user_input:
            product_data["needs_user_input"] = True
            product_data["user_input_type"] = "model_name"
            product_data["user_input_prompt"] = (
                "사진만으로 모델명을 정확히 식별하지 못했습니다. "
                "모델명을 직접 입력해 주세요. "
                "모델명이 잘 보이도록 다시 촬영한 사진을 올려도 됩니다."
            )
        else:
            product_data["needs_user_input"] = False
            product_data.pop("user_input_type", None)
            product_data.pop("user_input_prompt", None)

        workflow_meta = session.get("workflow_meta_jsonb", {}) or {}
        workflow_meta["checkpoint"] = (
            "A_needs_user_input" if needs_user_input else "A_before_confirm"
        )

        updated = self.session_repository.update(
            session_id=session_id,
            payload={
                "status": "awaiting_product_confirmation",
                "product_data_jsonb": product_data,
                "workflow_meta_jsonb": workflow_meta,
            },
        )

        if not updated:
            raise ValueError(f"Failed to analyze session: {session_id}")

        updated_product_data = updated.get("product_data_jsonb", {}) or {}

        return {
            "session_id": updated["id"],
            "status": updated["status"],
            "needs_user_input": updated_product_data.get("needs_user_input", False),
            "user_input_prompt": updated_product_data.get("user_input_prompt"),
            "product_data_jsonb": updated_product_data,
        }

    def confirm_product(self, session_id: str, candidate_index: int):
        session = self.session_repository.get_by_id(session_id)

        if not session:
            raise ValueError(f"Session not found: {session_id}")

        if session.get("status") != "awaiting_product_confirmation":
            raise ValueError(
                f"Session not ready for confirmation: {session.get('status')}"
            )

        product_data = session.get("product_data_jsonb", {}) or {}
        candidates = product_data.get("candidates", [])

        if not candidates:
            raise ValueError("No candidates available")

        if candidate_index < 0 or candidate_index >= len(candidates):
            raise ValueError("Invalid candidate index")

        if product_data.get("needs_user_input", False):
            raise ValueError(
                "Low confidence product. Please provide model name manually."
            )

        confirmed = candidates[candidate_index]

        normalized_model = self._normalize_text(confirmed.get("model"))
        confidence = float(confirmed.get("confidence", 0.0) or 0.0)

        if not normalized_model or confidence < 0.6:
            raise ValueError(
                "Low confidence product. Please provide model name manually."
            )

        product_data["confirmed_product"] = {
            **confirmed,
            "source": confirmed.get("source", "vision"),
        }
        product_data["needs_user_input"] = False
        product_data.pop("user_input_type", None)
        product_data.pop("user_input_prompt", None)

        workflow_meta = session.get("workflow_meta_jsonb", {}) or {}
        workflow_meta["checkpoint"] = "A_complete"

        updated = self.session_repository.update(
            session_id=session_id,
            payload={
                "status": "product_confirmed",
                "product_data_jsonb": product_data,
                "workflow_meta_jsonb": workflow_meta,
            },
        )

        if not updated:
            raise ValueError("Failed to confirm product")

        return {
            "session_id": updated["id"],
            "status": updated["status"],
            "product_data_jsonb": updated.get("product_data_jsonb", {}),
        }

    def provide_product_info(
        self,
        session_id: str,
        model: str,
        brand: str | None = None,
        category: str | None = None,
    ):
        session = self.session_repository.get_by_id(session_id)

        if not session:
            raise ValueError(f"Session not found: {session_id}")

        if session.get("status") != "awaiting_product_confirmation":
            raise ValueError(
                f"Session not ready for manual product input: {session.get('status')}"
            )

        normalized_model = self._normalize_text(model)
        normalized_brand = self._normalize_text(brand)
        normalized_category = self._normalize_text(category)

        if not normalized_model:
            raise ValueError("Model name is required")

        product_data = session.get("product_data_jsonb", {}) or {}

        confirmed_product = {
            "brand": normalized_brand or "Unknown",
            "model": normalized_model,
            "category": normalized_category or "unknown",
            "confidence": 1.0,
            "source": "user_input",
        }

        product_data["confirmed_product"] = confirmed_product
        product_data["needs_user_input"] = False
        product_data.pop("user_input_type", None)
        product_data.pop("user_input_prompt", None)

        workflow_meta = session.get("workflow_meta_jsonb", {}) or {}
        workflow_meta["checkpoint"] = "A_complete"

        updated = self.session_repository.update(
            session_id=session_id,
            payload={
                "status": "product_confirmed",
                "product_data_jsonb": product_data,
                "workflow_meta_jsonb": workflow_meta,
            },
        )

        if not updated:
            raise ValueError("Failed to save manual product info")

        return {
            "session_id": updated["id"],
            "status": updated["status"],
            "product_data_jsonb": updated.get("product_data_jsonb", {}),
        }

    def generate_listing(self, session_id: str):
        session = self.session_repository.get_by_id(session_id)

        if not session:
            raise ValueError(f"Session not found: {session_id}")

        if session.get("status") not in {
            "product_confirmed",
            "awaiting_product_confirmation",
        }:
            raise ValueError(
                f"Session not ready for listing generation: {session.get('status')}"
            )

        try:
            result_payload = self.seller_copilot_service.run_product_analysis_and_listing_pipeline(
                session_id=session_id,
                session_record=session,
            )
        except Exception as e:
            raise ValueError(f"Listing generation failed: {str(e)}")

        updated = self.session_repository.update(
            session_id=session_id,
            payload={
                "status": result_payload["status"],
                "selected_platforms_jsonb": result_payload.get(
                    "selected_platforms_jsonb", []
                ),
                "product_data_jsonb": result_payload.get("product_data_jsonb", {}),
                "listing_data_jsonb": result_payload.get("listing_data_jsonb", {}),
                "workflow_meta_jsonb": result_payload.get("workflow_meta_jsonb", {}),
            },
        )

        if not updated:
            raise ValueError("Failed to generate listing")

        return {
            "session_id": updated["id"],
            "status": updated["status"],
            "listing_data_jsonb": updated.get("listing_data_jsonb", {}),
        }

    def prepare_publish(self, session_id: str, platform_targets: list[str]):
        session = self.session_repository.get_by_id(session_id)

        if not session:
            raise ValueError(f"Session not found: {session_id}")

        if session.get("status") not in {
            "draft_generated",
            "awaiting_publish_approval",
        }:
            raise ValueError(
                f"Session not ready for publish preparation: {session.get('status')}"
            )

        if not platform_targets:
            raise ValueError("No platform targets provided")

        listing_data = session.get("listing_data_jsonb", {}) or {}
        canonical_listing = listing_data.get("canonical_listing")
        market_context = listing_data.get("market_context", {}) or {}

        if not canonical_listing:
            raise ValueError("No canonical listing found")

        canonical_price = int(canonical_listing.get("price", 0) or 0)
        sample_count = int(market_context.get("sample_count", 0) or 0)

        if canonical_price <= 0:
            raise ValueError(
                "Listing price is invalid. Market analysis or pricing strategy must be completed first."
            )

        if sample_count <= 0:
            raise ValueError(
                "Market sample count is too low. Cannot prepare publish without valid market context."
            )

        platform_packages = {}
        for platform in platform_targets:
            if platform == "bunjang":
                platform_price = canonical_price + 10000
            elif platform == "daangn":
                platform_price = max(canonical_price - 4000, 0)
            else:
                platform_price = canonical_price

            platform_packages[platform] = {
                "title": canonical_listing.get("title", ""),
                "body": canonical_listing.get("description", ""),
                "price": platform_price,
                "images": canonical_listing.get("images", []),
            }

        listing_data["platform_packages"] = platform_packages

        workflow_meta = session.get("workflow_meta_jsonb", {}) or {}
        workflow_meta["checkpoint"] = "C_prepared"

        updated = self.session_repository.update(
            session_id=session_id,
            payload={
                "status": "awaiting_publish_approval",
                "selected_platforms_jsonb": platform_targets,
                "listing_data_jsonb": listing_data,
                "workflow_meta_jsonb": workflow_meta,
            },
        )

        if not updated:
            raise ValueError("Failed to prepare publish")

        return {
            "session_id": updated["id"],
            "status": updated["status"],
            "listing_data_jsonb": updated.get("listing_data_jsonb", {}),
        }

    def publish_session(self, session_id: str):
        session = self.session_repository.get_by_id(session_id)

        if not session:
            raise ValueError(f"Session not found: {session_id}")

        if session.get("status") != "awaiting_publish_approval":
            raise ValueError(
                f"Session not ready for publish: {session.get('status')}"
            )

        selected_platforms = session.get("selected_platforms_jsonb", []) or []
        listing_data = session.get("listing_data_jsonb", {}) or {}
        platform_packages = listing_data.get("platform_packages", {}) or {}

        if not selected_platforms:
            raise ValueError("No selected platforms found")

        if not platform_packages:
            raise ValueError("No platform packages found")

        publish_results = {}
        any_failure = False

        for platform in selected_platforms:
            payload = platform_packages.get(platform)

            if not payload:
                publish_results[platform] = {
                    "success": False,
                    "platform": platform,
                    "error_code": "missing_platform_package",
                    "error_message": f"No platform package found for {platform}",
                }
                any_failure = True
                continue

            try:
                result = asyncio.run(
                    self.publish_service.publish(platform=platform, payload=payload)
                )

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
                    "evidence_path": None,
                }
                any_failure = True

        workflow_meta = session.get("workflow_meta_jsonb", {}) or {}
        workflow_meta["checkpoint"] = "C_complete"
        workflow_meta["publish_results"] = publish_results

        final_status = "failed" if any_failure else "completed"

        updated = self.session_repository.update(
            session_id=session_id,
            payload={
                "status": final_status,
                "workflow_meta_jsonb": workflow_meta,
            },
        )

        if not updated:
            raise ValueError("Failed to publish session")

        return {
            "session_id": updated["id"],
            "status": updated["status"],
            "workflow_meta_jsonb": updated.get("workflow_meta_jsonb", {}),
        }