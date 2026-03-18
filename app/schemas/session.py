from typing import Any

from pydantic import BaseModel, Field


class UploadImagesRequest(BaseModel):
    image_urls: list[str]


class ConfirmProductRequest(BaseModel):
    candidate_index: int


class ProvideProductInfoRequest(BaseModel):
    model: str
    brand: str | None = None
    category: str | None = None


class PreparePublishRequest(BaseModel):
    platform_targets: list[str]


class ProductView(BaseModel):
    image_paths: list[str] = Field(default_factory=list)
    image_count: int = 0
    analysis_source: str | None = None
    candidates: list[dict[str, Any]] = Field(default_factory=list)
    confirmed_product: dict[str, Any] | None = None


class ListingView(BaseModel):
    market_context: dict[str, Any] | None = None
    strategy: dict[str, Any] | None = None
    canonical_listing: dict[str, Any] | None = None
    platform_packages: dict[str, Any] = Field(default_factory=dict)


class PublishView(BaseModel):
    results: dict[str, Any] = Field(default_factory=dict)


class DebugView(BaseModel):
    graph_debug_logs: list[str] = Field(default_factory=list)
    validation_result: dict[str, Any] | None = None
    last_error: Any | None = None


class SessionUIResponse(BaseModel):
    session_id: str
    status: str
    checkpoint: str | None = None
    next_action: str | None = None
    needs_user_input: bool = False
    user_input_prompt: str | None = None
    selected_platforms: list[str] = Field(default_factory=list)

    product: ProductView
    listing: ListingView
    publish: PublishView
    debug: DebugView


CreateSessionResponse = SessionUIResponse
SessionDetailResponse = SessionUIResponse
UploadImagesResponse = SessionUIResponse
AnalyzeSessionResponse = SessionUIResponse
ConfirmProductResponse = SessionUIResponse
ProvideProductInfoResponse = SessionUIResponse
GenerateListingResponse = SessionUIResponse
PreparePublishResponse = SessionUIResponse
PublishResponse = SessionUIResponse