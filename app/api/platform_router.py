"""플랫폼 연동(로그인) API 라우터."""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from app.core.auth import AuthenticatedUser, get_current_user
from app.services.platform_auth_service import (
    get_session_status,
    open_login_browser,
    store_platform_session,
    verify_platform_session,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/platforms", tags=["platforms"])

# ── Connect Token 관리 (in-memory, 1회용) ────────────────────────

import uuid
import time

_connect_tokens: dict[str, dict[str, Any]] = {}
_TOKEN_TTL_SECONDS = 600  # 10분


def _cleanup_expired_tokens() -> None:
    now = time.time()
    expired = [k for k, v in _connect_tokens.items() if v["expires_at"] < now]
    for k in expired:
        del _connect_tokens[k]


class ConnectSessionRequest(BaseModel):
    storage_state: dict[str, Any]
    connect_token: str


# ── 엔드포인트 ────────────────────────────────────────────────────


@router.get("/status")
async def platform_status(user: AuthenticatedUser = Depends(get_current_user)):
    """각 플랫폼의 로그인 세션 상태를 확인한다."""
    return {"platforms": get_session_status(user_id=user.user_id)}


@router.post("/{platform}/login")
async def platform_login(platform: str):
    """Playwright 브라우저를 열어 사용자가 직접 로그인한다. (로컬 개발용)"""
    result = await open_login_browser(platform)
    return result


@router.post("/connect/start")
async def start_connect(user: AuthenticatedUser = Depends(get_current_user)):
    """Connect token 발급. 익스텐션이 세션 업로드 시 이 토큰으로 사용자 식별."""
    _cleanup_expired_tokens()

    token = uuid.uuid4().hex
    _connect_tokens[token] = {
        "user_id": user.user_id,
        "expires_at": time.time() + _TOKEN_TTL_SECONDS,
        "used": False,
    }
    logger.info("connect_token_issued user=%s", user.user_id)
    return {
        "connect_token": token,
        "expires_at": int(time.time() + _TOKEN_TTL_SECONDS),
    }


@router.post("/{platform}/connect")
async def connect_platform(platform: str, body: ConnectSessionRequest):
    """익스텐션에서 쿠키를 업로드하여 플랫폼 연결."""
    if platform not in ("bunjang", "joongna"):
        raise HTTPException(status_code=400, detail=f"지원하지 않는 플랫폼: {platform}")

    # 1. Token 검증 (1회용 강제)
    _cleanup_expired_tokens()
    token_data = _connect_tokens.get(body.connect_token)
    if not token_data:
        raise HTTPException(status_code=401, detail="유효하지 않거나 만료된 연결 토큰")
    if token_data["used"]:
        del _connect_tokens[body.connect_token]
        raise HTTPException(status_code=401, detail="이미 사용된 연결 토큰")
    if token_data["expires_at"] < time.time():
        del _connect_tokens[body.connect_token]
        raise HTTPException(status_code=401, detail="만료된 연결 토큰")

    # 즉시 사용 처리 (1회용)
    token_data["used"] = True
    user_id = token_data["user_id"]

    # 2. storage_state 검증
    cookies = body.storage_state.get("cookies", [])
    if not cookies:
        raise HTTPException(status_code=400, detail="쿠키가 비어있습니다")

    # 3. 암호화 저장
    store_platform_session(
        user_id=user_id,
        platform=platform,
        storage_state=body.storage_state,
    )
    logger.info("platform_session_stored user=%s platform=%s cookies=%d",
                user_id, platform, len(cookies))

    # 4. 즉시 검증 (retry 1회)
    verified, reason = await verify_platform_session(user_id, platform)

    # 5. 토큰 정리
    del _connect_tokens[body.connect_token]

    status = "connected" if verified else "reconnect_required"
    logger.info("platform_connect user=%s platform=%s status=%s reason=%s",
                user_id, platform, status, reason)

    return {
        "success": verified,
        "status": status,
        "reason": reason,
        "platform": platform,
    }
