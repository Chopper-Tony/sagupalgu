from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, TypedDict


CheckpointLiteral = Literal[
    "A_before_confirm",
    "A_needs_user_input",
    "A_complete",
    "B_market_complete",
    "B_strategy_complete",
    "B_draft_complete",
    "B_validation_failed",
    "B_complete",
    "C_prepared",
]

StatusLiteral = Literal[
    "session_created",
    "images_uploaded",
    "awaiting_product_confirmation",
    "product_confirmed",
    "market_analyzing",
    "draft_generated",
    "awaiting_publish_approval",
    "publishing",
    "completed",
    "failed",
]


class ProductCandidate(TypedDict, total=False):
    brand: str
    model: str
    category: str
    confidence: float
    storage: str


class ConfirmedProduct(TypedDict, total=False):
    brand: str
    model: str
    category: str
    confidence: float
    source: str
    storage: str


class MarketContext(TypedDict, total=False):
    price_band: List[int]
    median_price: Optional[int]
    sample_count: int
    crawler_sources: List[str]


class PricingStrategy(TypedDict, total=False):
    goal: str
    recommended_price: int
    negotiation_policy: str


class CanonicalListingProduct(TypedDict, total=False):
    brand: str
    model: str
    category: str
    confidence: float
    source: str
    storage: str


class CanonicalListing(TypedDict, total=False):
    title: str
    description: str
    tags: List[str]
    price: int
    images: List[str]
    strategy: str
    product: CanonicalListingProduct


class PlatformPackage(TypedDict, total=False):
    title: str
    body: str
    price: int
    images: List[str]
    category: str


class ValidationIssue(TypedDict, total=False):
    code: str
    message: str
    severity: Literal["info", "warning", "error"]


class ValidationResult(TypedDict, total=False):
    passed: bool
    issues: List[ValidationIssue]


class PublishResultSummary(TypedDict, total=False):
    success: bool
    platform: str
    error_code: Optional[str]
    error_message: Optional[str]
    external_url: Optional[str]
    external_listing_id: Optional[str]
    evidence_path: Optional[str]


class SellerCopilotState(TypedDict, total=False):
    """
    Seller Copilot LangGraph 상태 정의.
    """

    # ------------------------------------------------------------------
    # Session / Workflow Meta
    # ------------------------------------------------------------------
    session_id: str
    status: StatusLiteral
    checkpoint: CheckpointLiteral
    schema_version: int

    # ------------------------------------------------------------------
    # Input
    # ------------------------------------------------------------------
    image_paths: List[str]
    selected_platforms: List[str]
    user_product_input: Dict[str, Any]

    # ------------------------------------------------------------------
    # Product Identification
    # ------------------------------------------------------------------
    product_candidates: List[ProductCandidate]
    confirmed_product: Optional[ConfirmedProduct]
    analysis_source: str
    needs_user_input: bool
    clarification_prompt: Optional[str]

    # ------------------------------------------------------------------
    # Market Intelligence
    # ------------------------------------------------------------------
    search_queries: List[str]
    market_context: Optional[MarketContext]

    # ------------------------------------------------------------------
    # Pricing Strategy
    # ------------------------------------------------------------------
    strategy: Optional[PricingStrategy]

    # ------------------------------------------------------------------
    # Listing Generation
    # ------------------------------------------------------------------
    canonical_listing: Optional[CanonicalListing]
    platform_packages: Dict[str, PlatformPackage]

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------
    validation_passed: bool
    validation_result: ValidationResult

    # ------------------------------------------------------------------
    # Publish Summary (optional, future connection)
    # ------------------------------------------------------------------
    publish_results: Dict[str, PublishResultSummary]

    # ------------------------------------------------------------------
    # Debug / Trace
    # ------------------------------------------------------------------
    debug_logs: List[str]
    last_error: Optional[str]

    # ------------------------------------------------------------------
    # Internal injected hooks
    # ------------------------------------------------------------------
    _product_identity_hook: Any
    _market_intelligence_hook: Any
    _copywriting_hook: Any
    _package_builder_hook: Any


def create_initial_seller_copilot_state(
    session_id: str,
    image_paths: List[str],
    selected_platforms: Optional[List[str]] = None,
    user_product_input: Optional[Dict[str, Any]] = None,
) -> SellerCopilotState:
    return SellerCopilotState(
        session_id=session_id,
        status="images_uploaded",
        checkpoint="A_before_confirm",
        schema_version=1,
        image_paths=image_paths,
        selected_platforms=selected_platforms or ["bunjang", "joongna"],
        user_product_input=user_product_input or {},
        product_candidates=[],
        confirmed_product=None,
        analysis_source="",
        needs_user_input=False,
        clarification_prompt=None,
        search_queries=[],
        market_context=None,
        strategy=None,
        canonical_listing=None,
        platform_packages={},
        validation_passed=False,
        validation_result=ValidationResult(
            passed=False,
            issues=[],
        ),
        publish_results={},
        debug_logs=[],
        last_error=None,
    )