from typing import Any

from pydantic import BaseModel, Field


class CreateSessionResponse(BaseModel):
    session_id: str
    status: str


class SessionDetailResponse(BaseModel):
    id: str = Field(..., alias="session_id")
    status: str
    product_data_jsonb: dict[str, Any]
    listing_data_jsonb: dict[str, Any]
    workflow_meta_jsonb: dict[str, Any]

    model_config = {"populate_by_name": True}


class UploadImagesRequest(BaseModel):
    image_urls: list[str]


class UploadImagesResponse(BaseModel):
    session_id: str
    status: str
    product_data_jsonb: dict[str, Any]


class AnalyzeSessionResponse(BaseModel):
    session_id: str
    status: str
    product_data_jsonb: dict[str, Any]


class ConfirmProductRequest(BaseModel):
    candidate_index: int


class ConfirmProductResponse(BaseModel):
    session_id: str
    status: str
    product_data_jsonb: dict[str, Any]


class ProvideProductInfoRequest(BaseModel):
    model: str
    brand: str | None = None
    category: str | None = None


class ProvideProductInfoResponse(BaseModel):
    session_id: str
    status: str
    product_data_jsonb: dict[str, Any]


class GenerateListingResponse(BaseModel):
    session_id: str
    status: str
    listing_data_jsonb: dict[str, Any]


class PreparePublishRequest(BaseModel):
    platform_targets: list[str]


class PreparePublishResponse(BaseModel):
    session_id: str
    status: str
    listing_data_jsonb: dict[str, Any]


class PublishResponse(BaseModel):
    session_id: str
    status: str
    workflow_meta_jsonb: dict[str, Any]