"""
Agent 4 (복구) — 게시 실패 복구

분류 (Target Architecture, 4+2+5):
  recovery_node  → Tool Agent (ReAct)
                   lc_diagnose_publish_failure_tool · lc_auto_patch_tool · lc_discord_alert_tool
                   세 도구 자율 선택. PR1~3 동안 변경 없음.
"""
from __future__ import annotations

import json

import logging

from app.graph.seller_copilot_state import SellerCopilotState
from app.graph.nodes.helpers import (
    _build_react_llm,
    _log,
    _record_error,
    _record_tool_call,
    _run_async,
    _safe_int,
)


def recovery_node(state: SellerCopilotState) -> SellerCopilotState:
    """
    게시 실패 후 복구 에이전트 (ReAct).
    LLM이 실패 상황을 분석해 자율적으로 툴 호출 순서와 조합을 결정한다:
    - lc_diagnose_publish_failure_tool: 원인 진단
    - lc_auto_patch_tool: 자동 패치 생성
    - lc_discord_alert_tool: Discord 알림 발송
    """
    _log(state, "agent4:recovery:start")

    from app.tools.agentic_tools import (
        lc_diagnose_publish_failure_tool,
        lc_auto_patch_tool,
        lc_discord_alert_tool,
    )

    publish_results = state.get("publish_results") or {}
    canonical = state.get("canonical_listing") or {}
    session_id = state.get("session_id", "unknown")

    failures = [
        {
            "platform": p,
            "error_code": r.get("error_code", "unknown"),
            "error_message": r.get("error_message", ""),
        }
        for p, r in publish_results.items()
        if not r.get("success")
    ]

    if not failures:
        state["should_retry_publish"] = False
        state["checkpoint"] = "D_complete"
        return state

    system_prompt = (
        "당신은 중고거래 플랫폼 게시 실패 복구 전문 에이전트입니다.\n"
        "실패한 각 플랫폼에 대해 다음 순서로 반드시 툴을 호출하세요:\n\n"
        "1. lc_diagnose_publish_failure_tool → 실패 원인 진단\n"
        "2. lc_auto_patch_tool → 진단 결과 기반 패치 생성\n"
        "3. lc_discord_alert_tool → 관리자에게 알림 발송\n\n"
        "모든 플랫폼 처리 후 최종 JSON을 반환하라:\n"
        '{"auto_recoverable": true/false, "should_retry": true/false, '
        '"summary": "한 줄 요약"}'
    )

    failures_desc = "\n".join([
        f"- 플랫폼: {f['platform']} | 에러코드: {f['error_code']} | 메시지: {f['error_message'][:80]}"
        for f in failures
    ])
    current_title = canonical.get("title", "")
    current_description = (canonical.get("description") or "")[:100]

    user_prompt = (
        f"게시 실패 목록:\n{failures_desc}\n\n"
        f"현재 판매글 제목: {current_title}\n"
        f"현재 판매글 설명(앞 100자): {current_description}\n"
        f"session_id: {session_id}\n\n"
        "위 실패 플랫폼 각각에 대해 진단 → 패치 → 알림 순으로 처리하고 "
        "최종 복구 가능 여부를 JSON으로 반환하라."
    )

    patches = []
    any_auto_recoverable = False

    try:
        from langchain_core.messages import HumanMessage

        llm = _build_react_llm()
        if llm is None:
            raise ValueError("LLM 초기화 실패")

        from langchain.agents import create_agent
        agent = create_agent(
            llm,
            [lc_diagnose_publish_failure_tool, lc_auto_patch_tool, lc_discord_alert_tool],
            system_prompt=system_prompt,
        )

        _log(state, "agent4:react_agent:invoking LLM with tools=[diagnose, auto_patch, discord_alert]")
        msgs = [HumanMessage(content=user_prompt)]
        result = _run_async(lambda: agent.ainvoke({"messages": msgs}))

        for msg in result.get("messages", []):
            if hasattr(msg, "tool_calls") and msg.tool_calls:
                for tc in msg.tool_calls:
                    _log(state, f"agent4:llm_selected_tool:{tc.get('name', '?')}")
                    _record_tool_call(state, {
                        "tool_name": tc.get("name", ""),
                        "input": tc.get("args", {}),
                        "output": None,
                        "success": True,
                    })

            content = getattr(msg, "content", "") or ""
            if content:
                try:
                    parsed = json.loads(content) if isinstance(content, str) else content
                    if isinstance(parsed, dict):
                        if "auto_executable" in parsed:
                            patches.append(parsed)
                            if parsed.get("auto_executable"):
                                any_auto_recoverable = True
                        elif "auto_recoverable" in parsed:
                            if parsed.get("auto_recoverable") or parsed.get("should_retry"):
                                any_auto_recoverable = True
                except (json.JSONDecodeError, ValueError, TypeError):
                    pass

        import re
        final_content = str(result["messages"][-1].content or "")
        _log(state, f"agent4:react_agent:final_response={final_content[:100]}")
        try:
            m = re.search(r'\{[^{}]*"auto_recoverable"[^{}]*\}', final_content, re.DOTALL)
            if m:
                final_json = json.loads(m.group(0))
                if final_json.get("auto_recoverable") or final_json.get("should_retry"):
                    any_auto_recoverable = True
        except (json.JSONDecodeError, ValueError, TypeError):
            pass

    except Exception as e:
        logging.getLogger(__name__).error("agent4 ReAct recovery agent failed", exc_info=True)
        _record_error(state, "recovery_node", f"react_agent failed: {e}")
        _log(state, f"agent4:react_agent:failed error={e} → fallback to direct tool calls")

        from app.tools.agentic_tools import (
            diagnose_publish_failure_tool,
            auto_patch_tool,
            discord_alert_tool,
        )
        for f in failures:
            platform = f["platform"]
            diag_call = diagnose_publish_failure_tool(
                platform=platform,
                error_code=f["error_code"],
                error_message=f["error_message"],
            )
            _record_tool_call(state, diag_call)
            diag = diag_call.get("output") or {}

            patch_call = _run_async(lambda: auto_patch_tool(
                platform=platform,
                likely_cause=diag.get("likely_cause", "unknown"),
                canonical_listing=canonical,
                session_id=session_id,
            ))
            _record_tool_call(state, patch_call)
            patch = patch_call.get("output") or {}
            patches.append(patch)

            if patch.get("auto_executable") or diag.get("auto_recoverable"):
                any_auto_recoverable = True

            alert_msg = (
                f"[{platform}] 게시 실패 | 원인: {diag.get('likely_cause')} | "
                f"패치: {patch.get('type')} | 자동실행: {patch.get('auto_executable')}"
            )
            _run_async(lambda: discord_alert_tool(
                message=alert_msg,
                session_id=session_id,
                level="error",
            ))

    state["patch_suggestions"] = patches
    state["should_retry_publish"] = any_auto_recoverable

    retry_count = _safe_int(state.get("publish_retry_count"), 0)
    if any_auto_recoverable and retry_count < 2:
        state["publish_retry_count"] = retry_count + 1
        state["checkpoint"] = "D_recovering"
        _log(state, f"agent4:recovery:auto_recoverable retry={retry_count + 1}")
    else:
        state["checkpoint"] = "D_publish_failed"
        state["status"] = "publishing_failed"
        _log(state, "agent4:recovery:not_recoverable → publishing_failed")

    return state
