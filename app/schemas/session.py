"""
세션 API 스키마 — Pydantic v2

모든 응답은 SessionUIResponse를 기반으로 하며,
중첩 필드(product/listing/publish/agent_trace/debug)는
구체적인 서브 스키마로 타입 지정.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


# ── 에러 응답 ──────────────────────────────────────────────────────

class ErrorResponse(BaseModel):
    error: str
    message: str


# ── 중첩 서브 스키마 ───────────────────────────────────────────────

class ProductInfo(BaseModel):
    image_paths: List[str] = Field(default_factory=list)
    image_count: int = 0
    analysis_source: Optional[str] = None
    candidates: List[Dict[str, Any]] = Field(default_factory=list)
    confirmed_product: Optional[Dict[str, Any]] = None


class ListingInfo(BaseModel):
    market_context: Optional[Dict[str, Any]] = None
    strategy: Optional[Dict[str, Any]] = None
    canonical_listing: Optional[Dict[str, Any]] = None
    platform_packages: Dict[str, Any] = Field(default_factory=dict)
    optimization_suggestion: Optional[Dict[str, Any]] = None


class PublishInfo(BaseModel):
    results: Dict[str, Any] = Field(default_factory=dict)
    diagnostics: List[Dict[str, Any]] = Field(default_factory=list)


class AgentTrace(BaseModel):
    tool_calls: List[Dict[str, Any]] = Field(default_factory=list)
    rewrite_history: List[Dict[str, Any]] = Field(default_factory=list)


class DebugInfo(BaseModel):
    last_error: Optional[str] = None


# ── 공통 응답 베이스 ───────────────────────────────────────────────

class SessionUIResponse(BaseModel):
    session_id: str
    status: str
    checkpoint: Optional[str] = None
    next_action: Optional[str] = None
    needs_user_input: bool = False
    user_input_prompt: Optional[str] = None
    selected_platforms: List[str] = Field(default_factory=list)
    product: ProductInfo = Field(default_factory=ProductInfo)
    listing: ListingInfo = Field(default_factory=ListingInfo)
    publish: PublishInfo = Field(default_factory=PublishInfo)
    agent_trace: AgentTrace = Field(default_factory=AgentTrace)
    debug: DebugInfo = Field(default_factory=DebugInfo)

    model_config = {"extra": "ignore"}


# ── 엔드포인트별 응답 (향후 필드 추가 여지 보존) ──────────────────

class CreateSessionResponse(SessionUIResponse):
    pass


class SessionDetailResponse(SessionUIResponse):
    pass


class UploadImagesResponse(SessionUIResponse):
    pass


class AnalyzeSessionResponse(SessionUIResponse):
    pass


class ConfirmProductResponse(SessionUIResponse):
    pass


class ProvideProductInfoResponse(SessionUIResponse):
    pass


class GenerateListingResponse(SessionUIResponse):
    pass


class PreparePublishResponse(SessionUIResponse):
    pass


class PublishResponse(SessionUIResponse):
    pass


class RewriteListingResponse(SessionUIResponse):
    pass


class SaleStatusResponse(SessionUIResponse):
    pass


# ── 요청 스키마 ────────────────────────────────────────────────────

class UploadImagesRequest(BaseModel):
    image_urls: List[str]


class ConfirmProductRequest(BaseModel):
    candidate_index: int = 0


class ProvideProductInfoRequest(BaseModel):
    model: str
    brand: Optional[str] = None
    category: Optional[str] = None


class PreparePublishRequest(BaseModel):
    platform_targets: List[str]


class RewriteListingRequest(BaseModel):
    instruction: str = Field(..., min_length=1, description="재작성 지시사항")


class SaleStatusRequest(BaseModel):
    sale_status: str = Field(..., description="sold | unsold | in_progress")
