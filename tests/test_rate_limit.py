"""
M91: Rate Limiting 테스트
"""
import pytest

pytestmark = pytest.mark.unit


class TestRateLimitLogic:

    def setup_method(self):
        from app.middleware.rate_limit import reset_rate_limiter
        reset_rate_limiter()

    def test_제한_이내_통과(self):
        from app.middleware.rate_limit import _is_rate_limited
        limited, remaining = _is_rate_limited("test-client:GET", limit=5)
        assert limited is False
        assert remaining == 4

    def test_제한_초과시_차단(self):
        from app.middleware.rate_limit import _is_rate_limited
        for _ in range(10):
            _is_rate_limited("flood-client:POST", limit=10)
        limited, remaining = _is_rate_limited("flood-client:POST", limit=10)
        assert limited is True
        assert remaining == 0

    def test_다른_클라이언트_독립(self):
        from app.middleware.rate_limit import _is_rate_limited
        for _ in range(5):
            _is_rate_limited("client-a:GET", limit=5)
        limited_a, _ = _is_rate_limited("client-a:GET", limit=5)
        limited_b, _ = _is_rate_limited("client-b:GET", limit=5)
        assert limited_a is True
        assert limited_b is False

    def test_이미지_업로드_제한(self):
        from app.middleware.rate_limit import _get_rate_limit
        limit = _get_rate_limit("POST", "/api/v1/sessions/123/images")
        assert limit == 5

    def test_세션_생성_제한(self):
        from app.middleware.rate_limit import _get_rate_limit
        limit = _get_rate_limit("POST", "/api/v1/sessions")
        assert limit == 10

    def test_get_기본_제한(self):
        from app.middleware.rate_limit import _get_rate_limit
        limit = _get_rate_limit("GET", "/api/v1/sessions/123")
        assert limit == 60

    def test_reset_초기화(self):
        from app.middleware.rate_limit import _is_rate_limited, reset_rate_limiter
        for _ in range(5):
            _is_rate_limited("reset-test:GET", limit=5)
        limited, _ = _is_rate_limited("reset-test:GET", limit=5)
        assert limited is True

        reset_rate_limiter()
        limited, _ = _is_rate_limited("reset-test:GET", limit=5)
        assert limited is False
