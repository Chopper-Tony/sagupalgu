from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.graph.seller_copilot_state import (
    CanonicalListing,
    ConfirmedProduct,
    MarketContext,
    PricingStrategy,
    ProductCandidate,
    SellerCopilotState,
    ValidationIssue,
    ValidationResult,
)


def _append_debug_log(state: SellerCopilotState, message: str) -> None:
    logs = state.get("debug_logs", [])
    logs.append(message)
    state["debug_logs"] = logs


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _merge_updates(state: SellerCopilotState, updates: Optional[Dict[str, Any]]) -> None:
    if not updates:
        return
    for key, value in updates.items():
        state[key] = value


def _build_search_queries(product: ConfirmedProduct) -> List[str]:
    brand = (product.get("brand") or "").strip()
    model = (product.get("model") or "").strip()
    category = (product.get("category") or "").strip()

    queries: List[str] = []

    if model:
        queries.append(model)
        queries.append(model.replace(" ", ""))

    if brand and model:
        queries.append(f"{brand} {model}")

    if model and category:
        queries.append(f"{model} {category}")

    deduped: List[str] = []
    seen = set()
    for q in queries:
        if q and q not in seen:
            deduped.append(q)
            seen.add(q)

    return deduped


def _build_clarification_prompt(
    image_paths: List[str],
    candidates: List[ProductCandidate],
) -> str:
    if not image_paths:
        return "상품 이미지가 없습니다. 이미지를 다시 업로드해주세요."

    if not candidates:
        return (
            "상품 정보를 정확히 파악하지 못했습니다. "
            "모델명을 직접 입력해주시거나, 제품 전면/후면이 잘 보이도록 다시 촬영해주세요."
        )

    return (
        "상품 정보가 불명확합니다. 모델명을 직접 입력해주시거나, "
        "제품 전면 전체와 후면 라벨/로고가 보이게 다시 촬영해주세요."
    )


def _normalize_confirmed_product(data: Dict[str, Any]) -> ConfirmedProduct:
    return ConfirmedProduct(
        brand=(data.get("brand") or "").strip(),
        model=(data.get("model") or "").strip(),
        category=(data.get("category") or "").strip(),
        confidence=float(data.get("confidence", 0.0) or 0.0),
        source=(data.get("source") or "").strip(),
        storage=(data.get("storage") or "").strip(),
    )


def _build_tags(product: ConfirmedProduct) -> List[str]:
    tags: List[str] = []

    model = (product.get("model") or "").strip()
    brand = (product.get("brand") or "").strip()
    category = (product.get("category") or "").strip()

    if model:
        tags.append(model.replace(" ", ""))
    if brand:
        tags.append(brand)
    if category:
        tags.append(category)

    tags.extend(["중고", "급처"])

    deduped: List[str] = []
    seen = set()
    for tag in tags:
        if tag and tag not in seen:
            deduped.append(tag)
            seen.add(tag)

    return deduped[:5]


def _build_title(product: ConfirmedProduct, strategy: PricingStrategy) -> str:
    brand = product.get("brand") or ""
    model = product.get("model") or ""
    goal = strategy.get("goal") or "fast_sell"
    negotiation_policy = strategy.get("negotiation_policy") or ""

    if goal == "fast_sell":
        if "negotiation" in negotiation_policy.lower():
            return f"{brand} {model} 빠른 판매 (소액 네고 가능)".strip()
        return f"{brand} {model} 빠른 판매".strip()

    return f"{brand} {model} 판매합니다".strip()


def _build_description(
    product: ConfirmedProduct,
    strategy: PricingStrategy,
    market_context: MarketContext,
) -> str:
    brand = product.get("brand") or ""
    model = product.get("model") or ""
    price = _safe_int(strategy.get("recommended_price"), 0)
    median_price = market_context.get("median_price")
    negotiation_policy = strategy.get("negotiation_policy") or ""

    desc_lines = [
        f"{brand} {model} 판매합니다.".strip(),
    ]

    if price > 0:
        desc_lines.append(
            f"빠른 거래를 위해 추천 가격인 {price:,}원에 판매합니다."
        )

    if median_price:
        desc_lines.append(
            f"현재 확인된 중고 시세 중앙값은 약 {median_price:,}원 수준입니다."
        )

    if "negotiation" in negotiation_policy.lower():
        desc_lines.append("소액 네고 가능합니다.")

    desc_lines.append("제품 상태는 실사진을 참고해주세요.")
    desc_lines.append("궁금한 점은 편하게 문의주세요.")

    return "\n".join(desc_lines)


def product_identity_node(state: SellerCopilotState) -> SellerCopilotState:
    _append_debug_log(state, "product_identity_node:start")

    user_input = state.get("user_product_input") or {}
    candidates = state.get("product_candidates", [])

    if user_input:
        confirmed = _normalize_confirmed_product(
            {
                "brand": user_input.get("brand"),
                "model": user_input.get("model"),
                "category": user_input.get("category"),
                "confidence": 1.0,
                "source": "user_input",
                "storage": user_input.get("storage", ""),
            }
        )
        state["confirmed_product"] = confirmed
        state["needs_user_input"] = False
        state["clarification_prompt"] = None
        state["checkpoint"] = "A_complete"
        state["status"] = "product_confirmed"
        _append_debug_log(state, "product_identity_node:user_input_confirmed")
        return state

    if not candidates:
        updates = state.get("_product_identity_hook_result")
        _merge_updates(state, updates)
        candidates = state.get("product_candidates", [])

    if not candidates:
        state["confirmed_product"] = None
        state["needs_user_input"] = True
        state["clarification_prompt"] = _build_clarification_prompt(
            image_paths=state.get("image_paths", []),
            candidates=[],
        )
        state["checkpoint"] = "A_needs_user_input"
        state["status"] = "awaiting_product_confirmation"
        _append_debug_log(state, "product_identity_node:no_candidates")
        return state

    best = candidates[0]
    confidence = float(best.get("confidence", 0.0) or 0.0)

    if confidence < 0.6 or (best.get("model") or "").lower() in {"unknown", ""}:
        state["confirmed_product"] = None
        state["needs_user_input"] = True
        state["clarification_prompt"] = _build_clarification_prompt(
            image_paths=state.get("image_paths", []),
            candidates=candidates,
        )
        state["checkpoint"] = "A_needs_user_input"
        state["status"] = "awaiting_product_confirmation"
        _append_debug_log(
            state,
            f"product_identity_node:low_confidence={confidence}",
        )
        return state

    confirmed = _normalize_confirmed_product(
        {
            "brand": best.get("brand"),
            "model": best.get("model"),
            "category": best.get("category"),
            "confidence": confidence,
            "source": best.get("source", "vision"),
            "storage": best.get("storage", ""),
        }
    )
    state["confirmed_product"] = confirmed
    state["needs_user_input"] = False
    state["clarification_prompt"] = None
    state["checkpoint"] = "A_complete"
    state["status"] = "product_confirmed"
    _append_debug_log(state, "product_identity_node:vision_confirmed")
    return state


def clarification_node(state: SellerCopilotState) -> SellerCopilotState:
    _append_debug_log(state, "clarification_node:start")

    if not state.get("clarification_prompt"):
        state["clarification_prompt"] = _build_clarification_prompt(
            image_paths=state.get("image_paths", []),
            candidates=state.get("product_candidates", []),
        )

    state["checkpoint"] = "A_needs_user_input"
    state["status"] = "awaiting_product_confirmation"
    _append_debug_log(state, "clarification_node:end")
    return state


def market_intelligence_node(state: SellerCopilotState) -> SellerCopilotState:
    _append_debug_log(state, "market_intelligence_node:start")

    product = state.get("confirmed_product")
    if not product:
        state["last_error"] = "confirmed_product is required before market analysis"
        state["status"] = "failed"
        _append_debug_log(state, "market_intelligence_node:missing_confirmed_product")
        return state

    queries = _build_search_queries(product)
    state["search_queries"] = queries

    updates = state.get("_market_intelligence_hook_result")
    _merge_updates(state, updates)

    if not state.get("market_context"):
        state["market_context"] = MarketContext(
            price_band=[],
            median_price=None,
            sample_count=0,
            crawler_sources=[],
        )

    state["checkpoint"] = "B_market_complete"
    state["status"] = "market_analyzing"
    _append_debug_log(
        state,
        f"market_intelligence_node:queries={queries}",
    )
    return state


def pricing_strategy_node(state: SellerCopilotState) -> SellerCopilotState:
    _append_debug_log(state, "pricing_strategy_node:start")

    market_context = state.get("market_context") or {}
    median_price = market_context.get("median_price")

    recommended_price = 0
    if median_price:
        recommended_price = int(round(int(median_price) * 0.97, -2))

    state["strategy"] = PricingStrategy(
        goal="fast_sell",
        recommended_price=recommended_price,
        negotiation_policy="small negotiation allowed",
    )

    state["checkpoint"] = "B_strategy_complete"
    _append_debug_log(
        state,
        f"pricing_strategy_node:recommended_price={recommended_price}",
    )
    return state


def copywriting_node(state: SellerCopilotState) -> SellerCopilotState:
    _append_debug_log(state, "copywriting_node:start")

    updates = state.get("_copywriting_hook_result")
    _merge_updates(state, updates)

    if state.get("canonical_listing"):
        state["checkpoint"] = "B_draft_complete"
        state["status"] = "draft_generated"
        _append_debug_log(state, "copywriting_node:service_hook_used")
        return state

    product = state.get("confirmed_product")
    strategy = state.get("strategy") or {}
    market_context = state.get("market_context") or {}

    if not product:
        state["last_error"] = "confirmed_product is required before copywriting"
        state["status"] = "failed"
        _append_debug_log(state, "copywriting_node:missing_confirmed_product")
        return state

    title = _build_title(product, strategy)
    description = _build_description(product, strategy, market_context)
    tags = _build_tags(product)
    price = _safe_int(strategy.get("recommended_price"), 0)

    canonical_listing = CanonicalListing(
        title=title,
        description=description,
        tags=tags,
        price=price,
        images=state.get("image_paths", []),
        strategy=strategy.get("goal", "fast_sell"),
        product={
            "brand": product.get("brand", ""),
            "model": product.get("model", ""),
            "category": product.get("category", ""),
            "confidence": product.get("confidence", 0.0),
            "source": product.get("source", ""),
            "storage": product.get("storage", ""),
        },
    )

    state["canonical_listing"] = canonical_listing
    state["checkpoint"] = "B_draft_complete"
    state["status"] = "draft_generated"
    _append_debug_log(state, "copywriting_node:end")
    return state


def validation_node(state: SellerCopilotState) -> SellerCopilotState:
    _append_debug_log(state, "validation_node:start")

    issues: List[ValidationIssue] = []
    canonical = state.get("canonical_listing") or {}
    product = state.get("confirmed_product") or {}
    market_context = state.get("market_context") or {}

    if not product.get("model"):
        issues.append(
            ValidationIssue(
                code="missing_model",
                message="상품 모델명이 없습니다.",
                severity="error",
            )
        )

    title = (canonical.get("title") or "").strip()
    if len(title) < 5:
        issues.append(
            ValidationIssue(
                code="title_too_short",
                message="판매 제목이 너무 짧습니다.",
                severity="error",
            )
        )

    description = (canonical.get("description") or "").strip()
    if len(description) < 20:
        issues.append(
            ValidationIssue(
                code="description_too_short",
                message="판매 설명이 너무 짧습니다.",
                severity="error",
            )
        )

    price = _safe_int(canonical.get("price"), 0)
    if price <= 0:
        issues.append(
            ValidationIssue(
                code="invalid_price",
                message="권장 가격이 유효하지 않습니다.",
                severity="error",
            )
        )

    sample_count = _safe_int(market_context.get("sample_count"), 0)
    if sample_count <= 0:
        issues.append(
            ValidationIssue(
                code="low_market_samples",
                message="시장 데이터 표본이 부족합니다.",
                severity="warning",
            )
        )

    passed = not any(issue["severity"] == "error" for issue in issues)

    state["validation_passed"] = passed
    state["validation_result"] = ValidationResult(
        passed=passed,
        issues=issues,
    )

    if passed:
        state["checkpoint"] = "B_complete"
    else:
        state["checkpoint"] = "B_validation_failed"

    _append_debug_log(
        state,
        f"validation_node:passed={passed}, issue_count={len(issues)}",
    )
    return state


def refinement_node(state: SellerCopilotState) -> SellerCopilotState:
    _append_debug_log(state, "refinement_node:start")

    canonical = state.get("canonical_listing") or {}
    market_context = state.get("market_context") or {}

    description = (canonical.get("description") or "").strip()
    if len(description) < 20:
        description = (
            description
            + "\n제품 상태는 실사진을 참고해주세요. 빠른 거래 원합니다."
        ).strip()
        canonical["description"] = description

    price = _safe_int(canonical.get("price"), 0)
    median_price = _safe_int(market_context.get("median_price"), 0)
    if price <= 0 and median_price > 0:
        canonical["price"] = int(round(median_price * 0.97, -2))

    state["canonical_listing"] = canonical
    _append_debug_log(state, "refinement_node:end")
    return state


def package_builder_node(state: SellerCopilotState) -> SellerCopilotState:
    _append_debug_log(state, "package_builder_node:start")

    updates = state.get("_package_builder_hook_result")
    _merge_updates(state, updates)

    if state.get("platform_packages"):
        state["checkpoint"] = "C_prepared"
        state["status"] = "awaiting_publish_approval"
        _append_debug_log(state, "package_builder_node:service_hook_used")
        return state

    canonical = state.get("canonical_listing") or {}
    product = (canonical.get("product") or {}) if canonical else {}
    category = product.get("category") or ""

    title = canonical.get("title") or ""
    description = canonical.get("description") or ""
    price = _safe_int(canonical.get("price"), 0)
    images = canonical.get("images") or []

    state["platform_packages"] = {
        "bunjang": {
            "title": title,
            "body": description,
            "price": price + 10000 if price > 0 else 0,
            "images": images,
            "category": category,
        },
        "joongna": {
            "title": title,
            "body": description,
            "price": price,
            "images": images,
            "category": category,
        },
    }

    state["checkpoint"] = "C_prepared"
    state["status"] = "awaiting_publish_approval"
    _append_debug_log(state, "package_builder_node:end")
    return state