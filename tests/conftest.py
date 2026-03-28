"""
공유 pytest 픽스처 — integration 테스트 전반에서 재사용.
"""
import pytest

from app.middleware.rate_limit import reset_rate_limiter


@pytest.fixture(autouse=True)
def _reset_rate_limit_global():
    """모든 테스트 전후 rate limiter 초기화."""
    reset_rate_limiter()
    yield
    reset_rate_limiter()


@pytest.fixture
def confirmed_product():
    return {
        "brand": "Apple",
        "model": "iPhone 15 Pro",
        "category": "smartphone",
        "confidence": 0.92,
        "source": "vision",
        "storage": "256GB",
    }


@pytest.fixture
def market_context():
    return {
        "price_band": [900000, 1100000],
        "median_price": 980000,
        "sample_count": 12,
        "crawler_sources": ["번개장터", "중고나라"],
    }


@pytest.fixture
def strategy():
    return {
        "goal": "fast_sell",
        "recommended_price": 950600,
        "negotiation_policy": "small negotiation allowed",
    }


@pytest.fixture
def canonical_listing(confirmed_product, strategy):
    return {
        "title": "Apple iPhone 15 Pro 256GB 판매합니다",
        "description": "깨끗하게 사용했습니다. 실사진 참고 부탁드립니다. 빠른 거래 원합니다.",
        "tags": ["iPhone15Pro", "Apple", "smartphone"],
        "price": 950600,
        "images": ["path/to/image.jpg"],
        "strategy": "fast_sell",
        "product": confirmed_product,
    }


@pytest.fixture
def base_state(confirmed_product, market_context, strategy, canonical_listing):
    """그래프 실행 중간 단계 상태"""
    return {
        "session_id": "test-session-001",
        "status": "product_confirmed",
        "checkpoint": "A_complete",
        "schema_version": 2,
        "image_paths": ["path/to/image.jpg"],
        "selected_platforms": ["bunjang", "joongna"],
        "user_product_input": {},
        "product_candidates": [],
        "confirmed_product": confirmed_product,
        "analysis_source": "vision",
        "needs_user_input": False,
        "clarification_prompt": None,
        "search_queries": [],
        "market_context": market_context,
        "strategy": strategy,
        "canonical_listing": canonical_listing,
        "platform_packages": {},
        "rewrite_instruction": None,
        "validation_passed": False,
        "validation_result": {"passed": False, "issues": []},
        "validation_retry_count": 0,
        "tool_calls": [],
        "publish_diagnostics": [],
        "publish_retry_count": 0,
        "publish_results": {},
        "sale_status": None,
        "optimization_suggestion": None,
        "followup_due_at": None,
        "error_history": [],
        "last_error": None,
        "debug_logs": [],
    }
