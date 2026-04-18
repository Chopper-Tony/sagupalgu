"""
JWT 인증 모듈.

Supabase Auth JWT를 검증하고 user_id를 추출한다.
dev/local 환경에서는 X-Dev-User-Id 헤더로 bypass 가능.

알고리즘 지원 (#249):
  - HS256: legacy Supabase 프로젝트 (shared secret = SUPABASE_JWT_SECRET)
  - ES256 / RS256: 모던 Supabase 프로젝트 (asymmetric, JWKS 엔드포인트에서 공개키 fetch)

보안 (#250 CTO 리뷰 5건):
  - ALLOWED_ALGS 화이트리스트 — header alg downgrade 공격 차단
  - aud / iss 검증 활성화 — 다른 issuer 토큰 차단
  - PyJWKClient lifespan 명시 (5분) + key rotation 시 1회 retry
  - 모든 실패 경로 401 강제 (auth 레이어는 절대 500 금지)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from fastapi import Depends, HTTPException, Request

logger = logging.getLogger(__name__)


# ── 보안 상수 (CTO #250 #1 — alg downgrade 차단) ─────────────────────
ALLOWED_ALGS: frozenset = frozenset({"HS256", "ES256", "RS256"})

# ── JWKS client TTL (CTO #250 #3 — key rotation 대응) ────────────────
_JWKS_LIFESPAN_SECONDS = 300   # 5분 — Supabase 권장 cache TTL
_JWKS_TIMEOUT_SECONDS = 10     # JWKS HTTP fetch 타임아웃

# ── Supabase 표준 audience ───────────────────────────────────────────
_EXPECTED_AUDIENCE = "authenticated"


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


# JWKS client 캐시 — Supabase URL 당 1개. PyJWKClient 가 내부적으로 키 캐싱.
_jwks_clients: dict = {}


def _get_jwks_client(supabase_url: str):
    """Supabase JWKS 엔드포인트용 PyJWKClient (URL 당 싱글턴).

    lifespan 명시: 5분 마다 JWKS 재 fetch — Supabase key rotation 자동 반영.
    """
    import jwt as _jwt

    if supabase_url not in _jwks_clients:
        jwks_uri = f"{supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json"
        _jwks_clients[supabase_url] = _jwt.PyJWKClient(
            jwks_uri,
            lifespan=_JWKS_LIFESPAN_SECONDS,
            timeout=_JWKS_TIMEOUT_SECONDS,
        )
    return _jwks_clients[supabase_url]


def _expected_issuer(supabase_url: str) -> str:
    """Supabase 가 발급하는 토큰의 iss claim. CTO #250 #2 — issuer 검증용."""
    return f"{supabase_url.rstrip('/')}/auth/v1"


def _fetch_signing_key_with_retry(jwks_client, token: str):
    """JWKS 에서 signing key fetch. 네트워크 실패 시 1회 retry (CTO #250 #5).

    PyJWKClient.get_signing_key_from_jwt 가 HTTP 호출 + key 매칭 둘 다 함.
    네트워크 일시 장애 / key rotation 직후 mismatch 모두 1회 재시도로 흡수.
    """
    try:
        return jwks_client.get_signing_key_from_jwt(token)
    except Exception as e:  # noqa: BLE001 — network/HTTP/parse 모두 포함
        logger.warning("jwks_fetch_first_attempt_failed: %s", e)
        try:
            return jwks_client.get_signing_key_from_jwt(token)
        except Exception as e2:  # noqa: BLE001
            logger.error("jwks_fetch_retry_failed: %s", e2)
            raise


def _decode_jwt(token: str) -> dict:
    """Supabase JWT를 디코딩·검증한다.

    PyJWT 설치 여부 + 토큰 alg 헤더에 따라:
    - PyJWT 미설치: payload 만 base64 디코딩 (개발용)
    - HS256: SUPABASE_JWT_SECRET 또는 service_role_key 로 검증
    - ES256 / RS256: SUPABASE_URL 의 JWKS 에서 공개키 fetch 후 검증

    모든 실패 경로는 401 (CTO #250 #4 — auth 레이어 500 절대 금지).
    """
    try:
        import jwt
    except ImportError:
        # PyJWT 미설치 시 base64 디코딩만 (개발 환경)
        import base64
        import json
        parts = token.split(".")
        if len(parts) != 3:
            raise HTTPException(status_code=401, detail="잘못된 토큰 형식입니다")
        try:
            payload_b64 = parts[1] + "=" * (4 - len(parts[1]) % 4)
            return json.loads(base64.urlsafe_b64decode(payload_b64))
        except Exception:
            raise HTTPException(status_code=401, detail="잘못된 토큰 형식입니다")

    from app.core.config import get_settings
    settings = get_settings()

    # 1) 토큰 header 에서 alg 추출
    try:
        header = jwt.get_unverified_header(token)
    except jwt.exceptions.DecodeError as e:
        logger.warning("jwt_header_decode_failed: %s", e)
        raise HTTPException(status_code=401, detail="잘못된 토큰 형식입니다")
    except Exception as e:  # noqa: BLE001 — 어떤 예외든 401 으로 차단
        logger.warning("jwt_header_unknown_error: %s", e)
        raise HTTPException(status_code=401, detail="잘못된 토큰 형식입니다")

    alg = header.get("alg", "")

    # 2) 화이트리스트 사전 검증 (CTO #250 #1 — downgrade 공격 차단)
    if alg not in ALLOWED_ALGS:
        logger.warning("jwt_disallowed_alg: %s allowed=%s", alg, sorted(ALLOWED_ALGS))
        raise HTTPException(status_code=401, detail=f"지원하지 않는 토큰 알고리즘입니다: {alg}")

    issuer = _expected_issuer(settings.supabase_url)

    try:
        if alg == "HS256":
            secret = getattr(settings, "supabase_jwt_secret", None) or settings.supabase_service_role_key
            payload = jwt.decode(
                token,
                secret,
                algorithms=["HS256"],
                audience=_EXPECTED_AUDIENCE,
                issuer=issuer,
            )
        else:
            # ES256 / RS256
            jwks_client = _get_jwks_client(settings.supabase_url)
            signing_key = _fetch_signing_key_with_retry(jwks_client, token)
            payload = jwt.decode(
                token,
                signing_key.key,
                algorithms=[alg],
                audience=_EXPECTED_AUDIENCE,
                issuer=issuer,
            )

        return payload
    except jwt.exceptions.PyJWTError as e:
        # InvalidSignatureError / ExpiredSignatureError / InvalidAudienceError /
        # InvalidIssuerError 등 모두 포함
        logger.warning("jwt_verify_failed alg=%s err=%s", alg, e)
        raise HTTPException(status_code=401, detail="토큰 검증에 실패했습니다")
    except HTTPException:
        # 위 _fetch_signing_key_with_retry 가 raise 한 401 그대로 통과
        raise
    except Exception as e:  # noqa: BLE001
        # 예상 못한 예외 — JWKS HTTP / 네트워크 / 기타 모두 401 으로 차단 (CTO #250 #4)
        logger.error("jwt_unexpected_error alg=%s err=%s", alg, e)
        raise HTTPException(status_code=401, detail="토큰 검증 중 오류가 발생했습니다")


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
    """인증이 선택적인 엔드포인트용. 익명 사용자를 반환한다."""
    try:
        return await get_current_user(request)
    except HTTPException:
        return AuthenticatedUser(user_id="anonymous")
