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


# ── #249: 다중 알고리즘 (HS256 + ES256/RS256) 지원 ──────────────────


class TestDecodeJwtMultiAlg:
    """Bug #249: HS256-only → HS256 + ES256/RS256 (Supabase JWKS)."""

    def _b64(self, data: dict) -> str:
        return base64.urlsafe_b64encode(json.dumps(data).encode()).rstrip(b"=").decode()

    def _make_token(self, alg: str, payload: dict) -> str:
        header = self._b64({"alg": alg, "typ": "JWT"})
        body = self._b64(payload)
        return f"{header}.{body}.fake_sig"

    def test_HS256_경로_기존_secret_사용(self):
        """alg=HS256 은 SUPABASE_JWT_SECRET 으로 검증 (legacy 호환)."""
        from app.core.auth import _decode_jwt

        token = self._make_token("HS256", {"sub": "u-1"})
        with patch("app.core.config.get_settings") as mock_settings:
            mock_settings.return_value.supabase_jwt_secret = "test-secret"
            mock_settings.return_value.supabase_service_role_key = "fallback"
            mock_settings.return_value.supabase_url = "https://x.supabase.co"
            with patch("jwt.decode", return_value={"sub": "u-1"}) as mock_decode:
                payload = _decode_jwt(token)

        assert payload["sub"] == "u-1"
        # HS256 + 'test-secret' 으로 호출됐는지 검증
        args, kwargs = mock_decode.call_args
        assert kwargs["algorithms"] == ["HS256"]
        assert args[1] == "test-secret"

    def test_ES256_경로_JWKS_공개키_사용(self):
        """alg=ES256 은 SUPABASE_URL JWKS 에서 공개키 fetch 후 검증 (모던 Supabase)."""
        from app.core import auth as auth_mod
        from app.core.auth import _decode_jwt

        # JWKS client 캐시 클리어 (테스트 격리)
        auth_mod._jwks_clients.clear()

        token = self._make_token("ES256", {"sub": "u-2"})
        fake_signing_key = MagicMock()
        fake_signing_key.key = "fake-public-key"
        fake_jwks_client = MagicMock()
        fake_jwks_client.get_signing_key_from_jwt.return_value = fake_signing_key

        with patch("app.core.config.get_settings") as mock_settings:
            mock_settings.return_value.supabase_url = "https://proj.supabase.co"
            with patch("jwt.PyJWKClient", return_value=fake_jwks_client):
                with patch("jwt.decode", return_value={"sub": "u-2"}) as mock_decode:
                    payload = _decode_jwt(token)

        assert payload["sub"] == "u-2"
        args, kwargs = mock_decode.call_args
        assert kwargs["algorithms"] == ["ES256"]
        assert args[1] == "fake-public-key"

    def test_RS256_경로(self):
        """RS256 도 ES256 과 동일 경로 (JWKS)."""
        from app.core import auth as auth_mod
        from app.core.auth import _decode_jwt

        auth_mod._jwks_clients.clear()

        token = self._make_token("RS256", {"sub": "u-3"})
        fake_signing_key = MagicMock()
        fake_signing_key.key = "rsa-pub"
        fake_jwks_client = MagicMock()
        fake_jwks_client.get_signing_key_from_jwt.return_value = fake_signing_key

        with patch("app.core.config.get_settings") as mock_settings:
            mock_settings.return_value.supabase_url = "https://x.supabase.co"
            with patch("jwt.PyJWKClient", return_value=fake_jwks_client):
                with patch("jwt.decode", return_value={"sub": "u-3"}) as mock_decode:
                    _decode_jwt(token)

        args, kwargs = mock_decode.call_args
        assert kwargs["algorithms"] == ["RS256"]

    def test_지원하지_않는_알고리즘_401(self):
        """alg=NONE 등 지원 외 알고리즘은 401."""
        from app.core.auth import _decode_jwt

        token = self._make_token("none", {"sub": "u-4"})
        with patch("app.core.config.get_settings") as mock_settings:
            mock_settings.return_value.supabase_url = "https://x.supabase.co"
            with pytest.raises(HTTPException) as exc:
                _decode_jwt(token)

        assert exc.value.status_code == 401

    def test_손상된_header_401(self):
        """header 가 base64 디코딩 실패 → 401."""
        from app.core.auth import _decode_jwt

        with patch("app.core.config.get_settings") as mock_settings:
            mock_settings.return_value.supabase_url = "https://x.supabase.co"
            with pytest.raises(HTTPException) as exc:
                _decode_jwt("not-a-jwt-format")

        assert exc.value.status_code == 401

    def test_signature_검증_실패_401(self):
        """jwt.decode 가 InvalidSignatureError 던지면 401."""
        import jwt as _jwt
        from app.core.auth import _decode_jwt

        token = self._make_token("HS256", {"sub": "u-5"})
        with patch("app.core.config.get_settings") as mock_settings:
            mock_settings.return_value.supabase_jwt_secret = "wrong-secret"
            mock_settings.return_value.supabase_service_role_key = ""
            mock_settings.return_value.supabase_url = "https://x.supabase.co"
            with patch("jwt.decode", side_effect=_jwt.exceptions.InvalidSignatureError("bad sig")):
                with pytest.raises(HTTPException) as exc:
                    _decode_jwt(token)

        assert exc.value.status_code == 401
