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
    "C_complete",
    "D_complete",
    "D_publish_failed",
    "D_recovering",
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
    "published",
    "completed",
    "publishing_failed",
    "failed",
    "awaiting_sale_status_update",
    "optimization_suggested",
]


class ProductCandidate(TypedDict, total=False):
    brand: str
    model: str
    category: str
    confidence: float
    storage: str
    source: str


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
    reference_listings: List[Dict[str, Any]]  # 크롤링된 유사 매물 (제목+가격)


class PricingStrategy(TypedDict, total=False):
    goal: str
    recommended_price: int
    negotiation_policy: str


class CanonicalListing(TypedDict, total=False):
    title: str
    description: str
    tags: List[str]
    price: int
    images: List[str]
    strategy: str
    product: Dict[str, Any]


class ValidationIssue(TypedDict, total=False):
    code: str
    message: str
    severity: Literal["info", "warning", "error"]


class ValidationResult(TypedDict, total=False):
    passed: bool
    issues: List[ValidationIssue]


# ── 에이전틱 워크플로우를 위한 추가 타입 ──────────────────────────────

class ToolCall(TypedDict, total=False):
    """에이전트가 실제로 어떤 도구를 호출했는지 기록"""
    tool_name: str
    input: Dict[str, Any]
    output: Any
    success: bool
    error: Optional[str]


class PublishDiagnostics(TypedDict, total=False):
    """검증·복구 에이전트가 분석한 게시 실패 원인"""
    platform: str
    error_code: str
    error_message: str
    likely_cause: str          # "login_expired" | "content_policy" | "network" | "unknown"
    patch_suggestion: str
    auto_recoverable: bool


class OptimizationSuggestion(TypedDict, total=False):
    """판매 후 최적화 에이전트 출력"""
    type: str                  # "price_drop" | "rewrite" | "platform_add"
    current_price: int
    suggested_price: int
    reason: str
    urgency: str               # "high" | "medium" | "low"


# ── 메인 State ──────────────────────────────────────────────────────

class SellerCopilotState(TypedDict, total=False):
    # Session / Workflow Meta
    session_id: str
    status: StatusLiteral
    checkpoint: CheckpointLiteral
    schema_version: int

    # Input
    image_paths: List[str]
    selected_platforms: List[str]
    user_product_input: Dict[str, Any]

    # Product Identification
    product_candidates: List[ProductCandidate]
    confirmed_product: Optional[ConfirmedProduct]
    analysis_source: str
    needs_user_input: bool
    clarification_prompt: Optional[str]

    # Market Intelligence
    search_queries: List[str]
    market_context: Optional[MarketContext]

    # Pricing Strategy
    strategy: Optional[PricingStrategy]

    # Listing Generation
    canonical_listing: Optional[CanonicalListing]
    platform_packages: Dict[str, Any]
    rewrite_instruction: Optional[str]       # 사용자 피드백 기반 재작성 지시

    # Validation
    validation_passed: bool
    validation_result: ValidationResult
    validation_retry_count: int              # 자동 refinement 재시도 횟수

    # ── 에이전틱 핵심 필드 ──────────────────────────────────────────

    # ── Mission Planner ──────────────────────────────────────────────
    mission_goal: str                           # fast_sell | balanced | profit_max
    plan: Dict[str, Any]                        # 현재 실행 계획
    plan_revision_count: int                    # replan 횟수
    max_replans: int                            # replan 최대 횟수 (기본 1)
    decision_rationale: List[str]               # 의사결정 근거 이력
    missing_information: List[str]              # 부족한 정보 목록

    # ── Pre-listing Clarification ───────────────────────────────────
    pre_listing_questions: List[Dict[str, Any]]     # [{id, question}]
    pre_listing_answers: Dict[str, str]             # {question_id: answer}
    pre_listing_done: bool                          # 질문 완료 여부

    # ── Critic / Rewrite 루프 ────────────────────────────────────────
    critic_score: int                           # 0~100
    critic_feedback: List[Dict[str, Any]]       # [{type, impact, reason}]
    critic_rewrite_instructions: List[str]      # critic이 발행한 수정 지시
    critic_retry_count: int                     # rewrite 재시도 횟수
    max_critic_retries: int                     # rewrite 최대 횟수 (기본 2)

    # 도구 호출 이력 (어떤 도구를 왜 선택했는지 추적)
    tool_calls: List[ToolCall]

    # 게시 실패 진단 (검증·복구 에이전트)
    publish_diagnostics: List[PublishDiagnostics]
    patch_suggestions: List[Dict[str, Any]]  # auto_patch_tool 결과 목록
    should_retry_publish: bool               # recovery_node → route_after_recovery 신호
    publish_retry_count: int                 # 게시 자동 재시도 횟수
    publish_results: Dict[str, Any]

    # 판매 후 최적화 (Agent 5)
    sale_status: Optional[str]              # "sold" | "unsold" | "in_progress"
    optimization_suggestion: Optional[OptimizationSuggestion]
    followup_due_at: Optional[str]

    # 에러 이력 (단순 last_error가 아닌 전체 히스토리)
    error_history: List[Dict[str, Any]]
    last_error: Optional[str]

    # Debug / Trace
    debug_logs: List[str]


def create_initial_state(
    session_id: str,
    image_paths: List[str],
    selected_platforms: Optional[List[str]] = None,
    user_product_input: Optional[Dict[str, Any]] = None,
) -> SellerCopilotState:
    return SellerCopilotState(
        session_id=session_id,
        status="images_uploaded",
        checkpoint="A_before_confirm",
        schema_version=2,
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
        rewrite_instruction=None,
        mission_goal="balanced",
        plan={},
        plan_revision_count=0,
        max_replans=1,
        decision_rationale=[],
        missing_information=[],
        pre_listing_questions=[],
        pre_listing_answers={},
        pre_listing_done=False,
        critic_score=0,
        critic_feedback=[],
        critic_rewrite_instructions=[],
        critic_retry_count=0,
        max_critic_retries=2,
        validation_passed=False,
        validation_result=ValidationResult(passed=False, issues=[]),
        validation_retry_count=0,
        tool_calls=[],
        publish_diagnostics=[],
        patch_suggestions=[],
        should_retry_publish=False,
        publish_retry_count=0,
        publish_results={},
        sale_status=None,
        optimization_suggestion=None,
        followup_due_at=None,
        error_history=[],
        last_error=None,
        debug_logs=[],
    )
