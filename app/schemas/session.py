from __future__ import annotations
from typing import Any, Dict, List, Optional
from pydantic import BaseModel


class SessionUIResponse(BaseModel):
    session_id: str
    status: str
    checkpoint: Optional[str] = None
    next_action: Optional[str] = None
    needs_user_input: bool = False
    user_input_prompt: Optional[str] = None
    selected_platforms: List[str] = []
    product: Dict[str, Any] = {}
    listing: Dict[str, Any] = {}
    publish: Dict[str, Any] = {}
    agent_trace: Dict[str, Any] = {}
    debug: Dict[str, Any] = {}

    model_config = {"extra": "allow"}


class CreateSessionResponse(SessionUIResponse):
    pass


class SessionDetailResponse(SessionUIResponse):
    pass


class UploadImagesRequest(BaseModel):
    image_urls: List[str]


class UploadImagesResponse(SessionUIResponse):
    pass


class AnalyzeSessionResponse(SessionUIResponse):
    pass


class ConfirmProductRequest(BaseModel):
    candidate_index: int = 0


class ConfirmProductResponse(SessionUIResponse):
    pass


class ProvideProductInfoRequest(BaseModel):
    model: str
    brand: Optional[str] = None
    category: Optional[str] = None


class ProvideProductInfoResponse(SessionUIResponse):
    pass


class GenerateListingResponse(SessionUIResponse):
    pass


class PreparePublishRequest(BaseModel):
    platform_targets: List[str]


class PreparePublishResponse(SessionUIResponse):
    pass


class PublishResponse(SessionUIResponse):
    pass