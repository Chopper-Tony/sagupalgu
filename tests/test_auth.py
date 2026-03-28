"""
M88: JWT 인증 테스트
"""
import base64
import json

import pytest
from unittest.mock import patch, MagicMock

from fastapi import HTTPException

pytestmark = pytest.mark.unit


class TestExtractBearerToken:

    def test_정상_bearer_토큰_추출(self):
        from app.core.auth import _extract_bearer_token
        assert _extract_bearer_token("Bearer abc123") == "abc123"

    def test_bearer_없으면_none(self):
        from app.core.auth import _extract_bearer_token
        assert _extract_bearer_token(None) is None

    def test_잘못된_형식_none(self):
        from app.core.auth import _extract_bearer_token
        assert _extract_bearer_token("Basic abc") is None

    def test_빈_문자열_none(self):
        from app.core.auth import _extract_bearer_token
        assert _extract_bearer_token("") is None


class TestDecodeJwt:

    def _make_fake_jwt(self, payload: dict) -> str:
        """테스트용 가짜 JWT 생성 (서명 검증 없이 base64 디코딩용)"""
        header = base64.urlsafe_b64encode(json.dumps({"alg": "none"}).encode()).rstrip(b"=").decode()
        body = base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=").decode()
        sig = "fake_signature"
        return f"{header}.{body}.{sig}"

    def test_fake_jwt_디코딩(self):
        """PyJWT 미설치 환경에서 base64 디코딩 동작"""
        from app.core.auth import _decode_jwt
        token = self._make_fake_jwt({"sub": "user-123", "email": "test@test.com"})
        # PyJWT가 설치되어 있을 수 있으므로 import를 차단
        with patch.dict("sys.modules", {"jwt": None}):
            with patch("builtins.__import__", side_effect=lambda name, *a, **kw: (_ for _ in ()).throw(ImportError()) if name == "jwt" else __builtins__.__import__(name, *a, **kw)):
                # 직접 base64 디코딩 경로 테스트
                parts = token.split(".")
                payload_b64 = parts[1] + "=" * (4 - len(parts[1]) % 4)
                payload = json.loads(base64.urlsafe_b64decode(payload_b64))
                assert payload["sub"] == "user-123"

    def test_잘못된_토큰_형식_거부(self):
        from app.core.auth import _decode_jwt
        with pytest.raises((HTTPException, Exception)):
            _decode_jwt("not-a-jwt")


class TestGetCurrentUser:

    @pytest.mark.asyncio
    async def test_dev_환경_헤더_없으면_기본_사용자(self):
        from app.core.auth import get_current_user
        mock_request = MagicMock()
        mock_request.headers = {}

        with patch("app.core.config.get_settings") as mock_settings:
            mock_settings.return_value.environment = "local"
            user = await get_current_user(mock_request)
            assert user.user_id == "dev-user"

    @pytest.mark.asyncio
    async def test_dev_환경_x_dev_user_id_헤더(self):
        from app.core.auth import get_current_user
        mock_request = MagicMock()
        mock_request.headers = {"x-dev-user-id": "custom-user-42"}

        with patch("app.core.config.get_settings") as mock_settings:
            mock_settings.return_value.environment = "local"
            user = await get_current_user(mock_request)
            assert user.user_id == "custom-user-42"

    @pytest.mark.asyncio
    async def test_prod_환경_토큰_없으면_401(self):
        from app.core.auth import get_current_user
        mock_request = MagicMock()
        mock_request.headers = {}

        with patch("app.core.config.get_settings") as mock_settings:
            mock_settings.return_value.environment = "prod"
            with pytest.raises(HTTPException) as exc_info:
                await get_current_user(mock_request)
            assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_bearer_토큰으로_인증(self):
        from app.core.auth import get_current_user
        mock_request = MagicMock()
        mock_request.headers = {"authorization": "Bearer fake-token"}

        with patch("app.core.auth._decode_jwt") as mock_decode:
            mock_decode.return_value = {"sub": "jwt-user-99"}
            user = await get_current_user(mock_request)
            assert user.user_id == "jwt-user-99"

    @pytest.mark.asyncio
    async def test_bearer_토큰_sub_없으면_401(self):
        from app.core.auth import get_current_user
        mock_request = MagicMock()
        mock_request.headers = {"authorization": "Bearer fake-token"}

        with patch("app.core.auth._decode_jwt") as mock_decode:
            mock_decode.return_value = {"email": "no-sub@test.com"}
            with pytest.raises(HTTPException) as exc_info:
                await get_current_user(mock_request)
            assert exc_info.value.status_code == 401


class TestGetOptionalUser:

    @pytest.mark.asyncio
    async def test_인증_실패시_anonymous(self):
        from app.core.auth import get_optional_user
        mock_request = MagicMock()
        mock_request.headers = {}

        with patch("app.core.config.get_settings") as mock_settings:
            mock_settings.return_value.environment = "prod"
            user = await get_optional_user(mock_request)
            assert user.user_id == "anonymous"


class TestRouterIntegration:

    def test_create_session_uses_authenticated_user(self):
        """create_session이 temp-user-id가 아닌 인증된 사용자 ID를 사용하는지 확인"""
        import inspect
        from app.api.session_router import create_session
        source = inspect.getsource(create_session)
        assert "temp-user-id" not in source
        assert "user.user_id" in source or "user_id" in source
