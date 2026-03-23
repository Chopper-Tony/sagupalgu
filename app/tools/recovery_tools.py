"""
Agent 4 툴 — 게시 실패 진단 + 자동 패치 + Discord 알림

툴:
  lc_diagnose_publish_failure_tool  — create_react_agent에 bind
  lc_auto_patch_tool                — create_react_agent에 bind
  lc_discord_alert_tool             — create_react_agent에 bind
  diagnose_publish_failure_tool     — 직접 호출용
  auto_patch_tool                   — 직접 호출용
  discord_alert_tool                — 직접 호출용
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict

from langchain_core.tools import tool

from app.tools._common import _extract_json, _make_tool_call

logger = logging.getLogger(__name__)


# ── LangChain Tool 버전 (create_react_agent bind) ─────────────────

@tool
def lc_diagnose_publish_failure_tool(
    platform: str,
    error_code: str,
    error_message: str,
) -> str:
    """
    게시 실패 원인을 분석하고 복구 가능 여부를 판단합니다.
    실패한 각 플랫폼에 대해 반드시 가장 먼저 호출하세요.
    반환: JSON {"likely_cause": str, "patch_suggestion": str, "auto_recoverable": bool}
    """
    result = diagnose_publish_failure_tool(
        platform=platform,
        error_code=error_code,
        error_message=error_message,
    )
    output = result.get("output", {})
    return json.dumps(output, ensure_ascii=False)


@tool
async def lc_auto_patch_tool(
    platform: str,
    likely_cause: str,
    session_id: str,
    current_title: str = "",
    current_description: str = "",
) -> str:
    """
    게시 실패 원인에 따라 자동 패치 방법을 생성합니다.
    lc_diagnose_publish_failure_tool 호출 후 반드시 호출하세요.
    likely_cause 값: login_expired | network | content_policy | unknown
    반환: JSON {"type": str, "action": str, "auto_executable": bool, "message": str}
    """
    canonical_listing = {"title": current_title, "description": current_description}
    result = await auto_patch_tool(
        platform=platform,
        likely_cause=likely_cause,
        canonical_listing=canonical_listing,
        session_id=session_id,
    )
    output = result.get("output", {})
    return json.dumps(output, ensure_ascii=False)


@tool
async def lc_discord_alert_tool(
    message: str,
    session_id: str,
    level: str = "error",
) -> str:
    """
    Discord로 게시 실패 알림을 발송합니다.
    진단과 패치 생성 후 반드시 호출하세요.
    level: error | warning | info
    반환: JSON {"sent": bool}
    """
    result = await discord_alert_tool(
        message=message,
        session_id=session_id,
        level=level,
    )
    output = result.get("output", {})
    return json.dumps(output, ensure_ascii=False)


# ── 내부 구현 / 직접 호출용 ────────────────────────────────────────

def diagnose_publish_failure_tool(
    platform: str,
    error_code: str,
    error_message: str,
) -> Dict[str, Any]:
    """게시 실패 원인 분석 및 복구 가능 여부 판단. 검증·복구 에이전트가 호출."""
    tool_input = {"platform": platform, "error_code": error_code, "error_message": error_message}
    msg_lower = (error_message or "").lower()
    code_lower = (error_code or "").lower()

    if any(k in msg_lower for k in ["login", "auth", "session", "credential", "세션"]):
        diagnosis = {"likely_cause": "login_expired", "patch_suggestion": "플랫폼 재로그인 후 세션 파일 갱신 필요", "auto_recoverable": False}
    elif any(k in msg_lower for k in ["timeout", "network", "connection", "refused"]):
        diagnosis = {"likely_cause": "network", "patch_suggestion": "네트워크 재시도 가능", "auto_recoverable": True}
    elif any(k in msg_lower for k in ["content", "policy", "prohibited", "banned"]):
        diagnosis = {"likely_cause": "content_policy", "patch_suggestion": "판매글 내용 검토 필요 (금칙어/정책 위반)", "auto_recoverable": False}
    elif "missing_platform_package" in code_lower:
        diagnosis = {"likely_cause": "missing_package", "patch_suggestion": "prepare-publish 단계를 다시 실행하세요", "auto_recoverable": False}
    else:
        diagnosis = {"likely_cause": "unknown", "patch_suggestion": "로그를 확인하고 수동 처리 필요", "auto_recoverable": False}

    output = {"platform": platform, "error_code": error_code, "error_message": error_message, **diagnosis}
    return _make_tool_call("diagnose_publish_failure_tool", tool_input, output, success=True)


async def auto_patch_tool(
    platform: str,
    likely_cause: str,
    canonical_listing: Dict[str, Any],
    session_id: str,
) -> Dict[str, Any]:
    """
    게시 실패 원인에 따라 자동 패치 방법을 생성한다. (Agent 4 핵심 툴)

    - login_expired: 세션 갱신 명령어 안내
    - content_policy: LLM으로 대체 제목/설명 자동 생성
    - network: 재시도 전략 반환
    - unknown: 수동 검토 안내
    """
    tool_input = {"platform": platform, "likely_cause": likely_cause, "session_id": session_id}
    try:
        if likely_cause == "login_expired":
            patch = {
                "type": "session_renewal",
                "action": "세션 갱신 필요",
                "command": "python scripts/manual/save_sessions.py",
                "auto_executable": False,
                "message": f"[{platform}] 로그인 세션이 만료되었습니다. save_sessions.py를 실행해 세션을 갱신하세요.",
            }

        elif likely_cause == "content_policy":
            original_title = canonical_listing.get("title", "")
            original_desc = canonical_listing.get("description", "")

            from app.core.config import settings
            import httpx

            alt_prompt = f"""다음 중고거래 판매글이 플랫폼 정책 위반으로 거절됐습니다.
정책을 준수하는 대안을 작성하세요.

원본 제목: {original_title}
원본 설명: {original_desc[:200]}

규칙:
- 과장 표현 제거
- 금칙어 사용 금지
- 간결하고 사실 기반으로 작성

JSON만 반환: {{"title": "string", "description": "string"}}"""

            alt_content = {}
            if settings.gemini_api_key:
                try:
                    url = (
                        "https://generativelanguage.googleapis.com/v1beta/models/"
                        f"{settings.gemini_listing_model}:generateContent"
                        f"?key={settings.gemini_api_key}"
                    )
                    async with httpx.AsyncClient(timeout=20.0) as client:
                        resp = await client.post(url, json={
                            "contents": [{"parts": [{"text": alt_prompt}]}],
                            "generationConfig": {"temperature": 0.2},
                        })
                        resp.raise_for_status()
                        text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
                        alt_content = _extract_json(text)
                except Exception as e:
                    logger.warning(f"[auto_patch_tool] content rewrite failed: {e}")

            patch = {
                "type": "content_rewrite",
                "action": "판매글 자동 재작성",
                "alternative_title": alt_content.get("title", original_title),
                "alternative_description": alt_content.get("description", original_desc),
                "auto_executable": bool(alt_content),
            }

        elif likely_cause == "network":
            patch = {
                "type": "retry",
                "action": "자동 재시도 예약",
                "retry_after_seconds": 30,
                "auto_executable": True,
                "message": f"[{platform}] 네트워크 오류. 30초 후 자동 재시도합니다.",
            }

        else:
            patch = {
                "type": "manual_review",
                "action": "수동 검토 필요",
                "auto_executable": False,
                "message": f"[{platform}] 자동 처리 불가. 로그를 확인하고 수동으로 처리하세요.",
            }

        return _make_tool_call("auto_patch_tool", tool_input, patch, success=True)

    except Exception as e:
        logger.error(f"[auto_patch_tool] failed: {e}")
        return _make_tool_call(
            "auto_patch_tool", tool_input,
            {"type": "error", "auto_executable": False, "message": str(e)},
            success=False, error=str(e),
        )


async def discord_alert_tool(
    message: str,
    session_id: str,
    level: str = "error",
) -> Dict[str, Any]:
    """게시 실패/시스템 이상 시 Discord로 알림. 검증·복구 에이전트가 호출."""
    tool_input = {"message": message, "session_id": session_id, "level": level}
    try:
        import os, httpx
        webhook_url = os.getenv("DISCORD_WEBHOOK_URL")
        if not webhook_url:
            return _make_tool_call("discord_alert_tool", tool_input, {"sent": False}, success=True)

        color = {"error": 0xFF0000, "warning": 0xFFA500, "info": 0x00BFFF}.get(level, 0xFF0000)
        payload = {
            "embeds": [{
                "title": f"[사구팔구] {level.upper()}",
                "description": message,
                "color": color,
                "fields": [{"name": "session_id", "value": session_id, "inline": True}],
            }]
        }
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(webhook_url, json=payload)
            resp.raise_for_status()
        return _make_tool_call("discord_alert_tool", tool_input, {"sent": True}, success=True)

    except Exception as e:
        return _make_tool_call("discord_alert_tool", tool_input, {"sent": False}, success=False, error=str(e))
