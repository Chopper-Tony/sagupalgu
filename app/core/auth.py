"""
JWT 인증 모듈.

Supabase Auth JWT를 검증하고 user_id를 추출한다.
dev/local 환경에서는 X-Dev-User-Id 헤더로 bypass 가능.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from fastapi import Depends, HTTPException, Request

logger = logging.getLogger(__name__)


@dataclass
class AuthenticatedUser:
    """인증된 사용자 정보."""
    user_id: str


def _extract_bearer_token(authorization: str | None) -> str | None:
    """Authorization 헤더에서 Bearer 토큰을 추출한다."""
    if not authorization:
        return None
    parts = authorization.split()
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1]
    return None


def _decode_jwt(token: str) -> dict:
    """Supabase JWT를 디코딩·검증한다.

    PyJWT 설치 여부에 따라:
    - 설치됨: 서명 검증 (HS256, SUPABASE_JWT_SECRET)
    - 미설치: payload만 디코딩 (개발용)
    """
    try:
        import jwt
        from app.core.config import get_settings
        settings = get_settings()
        secret = getattr(settings, "supabase_jwt_secret", None) or settings.supabase_service_role_key
        payload = jwt.decode(
            token,
            secret,
            algorithms=["HS256"],
            audience="authenticated",
            options={"verify_aud": False},
        )
        return payload
    except ImportError:
        # PyJWT 미설치 시 base64 디코딩만 (개발 환경)
        import base64
        import json
        parts = token.split(".")
        if len(parts) != 3:
            raise HTTPException(status_code=401, detail="잘못된 토큰 형식입니다")
        payload_b64 = parts[1] + "=" * (4 - len(parts[1]) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        return payload
    except (ValueError, KeyError) as e:
        logger.warning("jwt_decode_failed: %s", e)
        raise HTTPException(status_code=401, detail="토큰 검증에 실패했습니다")


async def get_current_user(request: Request) -> AuthenticatedUser:
    """요청에서 인증된 사용자를 추출한다.

    인증 순서:
    1. Authorization: Bearer <jwt> → JWT에서 user_id (sub) 추출
    2. X-Dev-User-Id 헤더 → dev/local 환경에서만 bypass
    3. 둘 다 없으면 401
    """
    from app.core.config import get_settings
    settings = get_settings()

    # 1. JWT 토큰 검증
    authorization = request.headers.get("authorization")
    token = _extract_bearer_token(authorization)
    if token:
        payload = _decode_jwt(token)
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="토큰에 사용자 정보가 없습니다")
        return AuthenticatedUser(user_id=user_id)

    # 2. Dev bypass 안전장치: prod에서 X-Dev-User-Id 절대 차단
    dev_user_header = request.headers.get("x-dev-user-id")
    if settings.environment == "prod" and dev_user_header:
        logger.warning("prod_dev_bypass_blocked: header=%s", dev_user_header)
        raise HTTPException(status_code=403, detail="Dev bypass는 프로덕션에서 사용할 수 없습니다")

    # 3. Dev bypass (local/dev 환경만)
    if settings.environment in ("local", "dev"):
        if dev_user_header:
            return AuthenticatedUser(user_id=dev_user_header)
        # local/dev에서 헤더 없으면 기본 사용자
        return AuthenticatedUser(user_id="dev-user")

    # 4. prod 환경에서 인증 없으면 401
    raise HTTPException(status_code=401, detail="인증이 필요합니다")


async def get_optional_user(request: Request) -> AuthenticatedUser:
    """인증이 선택적인 엔드포인트용. ���상 사용자를 반환한다."""
    try:
        return await get_current_user(request)
    except HTTPException:
        return AuthenticatedUser(user_id="anonymous")
