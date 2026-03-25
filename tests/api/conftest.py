"""API 통합 테스트 공유 픽스처."""
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.dependencies import get_session_service
from app.main import app

BASE = "/api/v1/sessions"

SESSION_UI = {
    "session_id": "sess-001",
    "status": "session_created",
    "checkpoint": None,
    "next_action": "upload_images",
    "needs_user_input": False,
    # 평탄화 필드 (프론트엔드 계약)
    "clarification_prompt": None,
    "image_urls": [],
    "product_candidates": [],
    "confirmed_product": None,
    "canonical_listing": None,
    "market_context": None,
    "platform_results": [],
    "optimization_suggestion": None,
    "rewrite_instruction": None,
    "last_error": None,
    "selected_platforms": [],
    # 중첩 필드 (하위 호환)
    "product": {
        "image_paths": [],
        "image_count": 0,
        "analysis_source": None,
        "candidates": [],
        "confirmed_product": None,
    },
    "listing": {
        "market_context": None,
        "strategy": None,
        "canonical_listing": None,
        "platform_packages": {},
        "optimization_suggestion": None,
    },
    "publish": {"results": {}, "diagnostics": []},
    "agent_trace": {"tool_calls": [], "rewrite_history": []},
    "debug": {"last_error": None},
}


@pytest.fixture
def mock_svc():
    svc = MagicMock()
    svc.create_session = AsyncMock(return_value=SESSION_UI)
    svc.get_session = AsyncMock(return_value=SESSION_UI)
    svc.attach_images = AsyncMock(return_value={**SESSION_UI, "status": "images_uploaded"})
    svc.analyze_session = AsyncMock(return_value={**SESSION_UI, "status": "awaiting_product_confirmation"})
    svc.confirm_product = AsyncMock(return_value={**SESSION_UI, "status": "product_confirmed"})
    svc.provide_product_info = AsyncMock(return_value={**SESSION_UI, "status": "product_confirmed"})
    svc.generate_listing = AsyncMock(return_value={**SESSION_UI, "status": "draft_generated"})
    svc.rewrite_listing = AsyncMock(return_value={**SESSION_UI, "status": "draft_generated"})
    svc.prepare_publish = AsyncMock(return_value={**SESSION_UI, "status": "awaiting_publish_approval"})
    svc.publish_session = AsyncMock(return_value={**SESSION_UI, "status": "completed"})
    svc.update_sale_status = AsyncMock(return_value={**SESSION_UI, "status": "awaiting_sale_status_update"})
    return svc


@pytest.fixture
def client(mock_svc):
    app.dependency_overrides[get_session_service] = lambda: mock_svc
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
