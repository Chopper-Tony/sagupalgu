"""
M91: Rate Limiting 테스트
M102: Rate Limit 키 재설계 — route_group 기반 독립 bucket
"""
import pytest

pytestmark = pytest.mark.unit


class TestRateLimitLogic:

    def setup_method(self):
        from app.middleware.rate_limit import reset_rate_limiter
        reset_rate_limiter()

    def test_제한_이내_통과(self):
        from app.middleware.rate_limit import _is_rate_limited
        limited, remaining = _is_rate_limited("test-client:get:default", limit=5)
        assert limited is False
        assert remaining == 4

    def test_제한_초과시_차단(self):
        from app.middleware.rate_limit import _is_rate_limited
        for _ in range(10):
            _is_rate_limited("flood-client:post:default", limit=10)
        limited, remaining = _is_rate_limited("flood-client:post:default", limit=10)
        assert limited is True
        assert remaining == 0

    def test_다른_클라이언트_독립(self):
        from app.middleware.rate_limit import _is_rate_limited
        for _ in range(5):
            _is_rate_limited("client-a:get:default", limit=5)
        limited_a, _ = _is_rate_limited("client-a:get:default", limit=5)
        limited_b, _ = _is_rate_limited("client-b:get:default", limit=5)
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
            _is_rate_limited("reset-test:get:default", limit=5)
        limited, _ = _is_rate_limited("reset-test:get:default", limit=5)
        assert limited is True

        reset_rate_limiter()
        limited, _ = _is_rate_limited("reset-test:get:default", limit=5)
        assert limited is False


class TestRouteGroup:
    """M102: route_group 분류 정확성 테스트."""

    def test_route_group_이미지(self):
        from app.middleware.rate_limit import _get_route_group
        assert _get_route_group("POST", "/api/v1/sessions/123/images") == "post:images"

    def test_route_group_세션_생성(self):
        from app.middleware.rate_limit import _get_route_group
        assert _get_route_group("POST", "/api/v1/sessions") == "post:sessions"

    def test_route_group_게시(self):
        from app.middleware.rate_limit import _get_route_group
        assert _get_route_group("POST", "/api/v1/sessions/123/publish") == "post:publish"

    def test_route_group_재작성(self):
        from app.middleware.rate_limit import _get_route_group
        assert _get_route_group("POST", "/api/v1/sessions/123/rewrite") == "post:rewrite"

    def test_route_group_기타_POST(self):
        from app.middleware.rate_limit import _get_route_group
        assert _get_route_group("POST", "/api/v1/sessions/123/confirm") == "post:default"

    def test_route_group_GET(self):
        from app.middleware.rate_limit import _get_route_group
        assert _get_route_group("GET", "/api/v1/sessions/123") == "get:default"


class TestRouteGroupBucketIsolation:
    """M102: 다른 route_group이 독립 bucket을 사용하는지 검증."""

    def setup_method(self):
        from app.middleware.rate_limit import reset_rate_limiter
        reset_rate_limiter()

    def test_다른_POST_경로_독립_bucket(self):
        """images(limit=5)와 sessions(limit=10)가 별도 bucket인지 확인."""
        from app.middleware.rate_limit import _is_rate_limited

        # images bucket을 한도까지 채움
        for _ in range(5):
            _is_rate_limited("client-x:post:images", limit=5)
        limited_images, _ = _is_rate_limited("client-x:post:images", limit=5)
        assert limited_images is True, "images bucket이 초과되어야 함"

        # sessions bucket은 독립이므로 아직 여유
        limited_sessions, remaining = _is_rate_limited("client-x:post:sessions", limit=10)
        assert limited_sessions is False, "sessions bucket은 별도여야 함"
        assert remaining == 9

    def test_같은_route_group_공유(self):
        """같은 route group 내 요청은 카운트를 공유한다."""
        from app.middleware.rate_limit import _is_rate_limited

        # 같은 bucket key로 3회
        for _ in range(3):
            _is_rate_limited("client-y:post:default", limit=5)

        # 동일 bucket이므로 누적됨
        limited, remaining = _is_rate_limited("client-y:post:default", limit=5)
        assert limited is False
        assert remaining == 1  # 5 - 4(3+1)

    def test_publish_rewrite_독립_bucket(self):
        """publish와 rewrite가 독립 bucket인지 확인."""
        from app.middleware.rate_limit import _is_rate_limited

        # publish bucket 10회 채움
        for _ in range(10):
            _is_rate_limited("client-z:post:publish", limit=10)
        limited_publish, _ = _is_rate_limited("client-z:post:publish", limit=10)
        assert limited_publish is True

        # rewrite bucket은 독립
        limited_rewrite, _ = _is_rate_limited("client-z:post:rewrite", limit=10)
        assert limited_rewrite is False
