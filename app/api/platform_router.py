"""플랫폼 연동(로그인) API 라우터."""
from fastapi import APIRouter

from app.services.platform_auth_service import get_session_status, open_login_browser

router = APIRouter(prefix="/platforms", tags=["platforms"])


@router.get("/status")
async def platform_status():
    """각 플랫폼의 로그인 세션 상태를 확인한다."""
    return {"platforms": get_session_status()}


@router.post("/{platform}/login")
async def platform_login(platform: str):
    """Playwright 브라우저를 열어 사용자가 직접 로그인한다.

    브라우저가 열리면 사용자가 로그인을 완료할 때까지 대기하고,
    완료 시 쿠키를 서버에 저장한 뒤 결과를 반환한다.
    """
    result = await open_login_browser(platform)
    return result
