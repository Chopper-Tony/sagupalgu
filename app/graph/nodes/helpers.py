"""
노드 공통 헬퍼 — 로깅, tool_call 기록, async 실행, LLM 초기화
"""
from __future__ import annotations

import asyncio
import threading
from datetime import datetime, timezone
from typing import Any, Dict

from app.core.utils import safe_int as _safe_int  # noqa: F401 — 노드 전역 import
from app.graph.seller_copilot_state import SellerCopilotState


def _log(state: SellerCopilotState, msg: str) -> None:
    logs = state.get("debug_logs") or []
    logs.append(f"[{datetime.now(timezone.utc).isoformat()}] {msg}")
    state["debug_logs"] = logs


import time as _time


def _start_timer() -> float:
    """노드 실행 시간 측정 시작."""
    return _time.monotonic()


def _record_node_timing(state: SellerCopilotState, node_name: str, start: float) -> None:
    """노드 실행 시간을 state에 기록."""
    elapsed = round(_time.monotonic() - start, 3)
    metrics = state.get("execution_metrics") or []
    metrics.append({
        "node": node_name,
        "elapsed_seconds": elapsed,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    state["execution_metrics"] = metrics
    _log(state, f"{node_name}:elapsed={elapsed}s")


def _record_tool_call(state: SellerCopilotState, call: Dict[str, Any]) -> None:
    calls = state.get("tool_calls") or []
    calls.append(call)
    state["tool_calls"] = calls


def _record_error(state: SellerCopilotState, source: str, error: str) -> None:
    history = state.get("error_history") or []
    history.append({
        "source": source,
        "error": error,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    state["error_history"] = history
    state["last_error"] = error


_dedicated_loop = None
_dedicated_thread = None
_loop_lock = threading.Lock()


def _get_dedicated_loop():
    """전용 이벤트루프 데몬 스레드. 최초 호출 시 생성, 이후 재사용."""
    global _dedicated_loop, _dedicated_thread
    if _dedicated_loop is not None and _dedicated_loop.is_running():
        return _dedicated_loop
    with _loop_lock:
        # double-check locking
        if _dedicated_loop is not None and _dedicated_loop.is_running():
            return _dedicated_loop
        import sys
        if sys.platform == "win32":
            loop = asyncio.SelectorEventLoop()
        else:
            loop = asyncio.new_event_loop()

        def _run_loop(lp):
            asyncio.set_event_loop(lp)
            lp.run_forever()

        thread = threading.Thread(target=_run_loop, args=(loop,), daemon=True)
        thread.start()
        _dedicated_loop = loop
        _dedicated_thread = thread
        return loop


def _run_async(coro_or_factory):
    """동기 컨텍스트에서 async 코드 실행. 전용 이벤트루프 스레드에 submit.

    ⚠️ 사용 범위 제한 원칙 (CTO2 P0):
    - graph 노드 내부에서만 사용 (app/graph/nodes/ 한정)
    - service/application layer로의 확산 금지
    - 추후 LangGraph native async 지원 시 제거 예정

    callable(lambda)이 전달되면 호출해서 코루틴을 생성한다.
    이를 통해 테스트에서 _run_async를 mock할 때 코루틴이 미리 생성되지 않아
    'coroutine never awaited' RuntimeWarning을 방지한다.
    """
    import inspect
    coro = (
        coro_or_factory()
        if callable(coro_or_factory) and not inspect.iscoroutine(coro_or_factory)
        else coro_or_factory
    )
    loop = _get_dedicated_loop()
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    return future.result(timeout=120)


def _build_react_llm():
    """ReAct 에이전트용 LLM 초기화 (bind_tools 지원 모델).
    LISTING_LLM_PROVIDER 설정에 따라 우선순위 결정."""
    from app.core.config import settings

    provider = settings.listing_llm_provider  # "openai" | "gemini" | "solar"

    # 1순위: 설정된 provider
    if provider == "openai":
        order = ["openai", "gemini"]
    elif provider == "solar":
        # Solar는 LangChain bind_tools 미지원 → OpenAI/Gemini fallback
        order = ["openai", "gemini"]
    else:
        order = ["gemini", "openai"]

    for p in order:
        try:
            if p == "gemini" and settings.gemini_api_key:
                from langchain_google_genai import ChatGoogleGenerativeAI
                return ChatGoogleGenerativeAI(
                    model=settings.gemini_listing_model,
                    google_api_key=settings.gemini_api_key,
                    temperature=0.0,
                )
            if p == "openai" and settings.openai_api_key:
                from langchain_openai import ChatOpenAI
                return ChatOpenAI(
                    model=settings.openai_listing_model,
                    api_key=settings.openai_api_key,
                    temperature=0.0,
                )
        except Exception:
            continue
    return None


def _extract_market_context(text: str) -> dict:
    """LLM 최종 응답에서 market_context JSON 파싱"""
    import json, re
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text).strip()
        text = re.sub(r"```$", "", text).strip()
    try:
        data = json.loads(text)
        return {
            "median_price": data.get("median_price"),
            "price_band": data.get("price_band") or [],
            "sample_count": int(data.get("sample_count") or 0),
            "crawler_sources": data.get("crawler_sources") or [],
        }
    except Exception:
        m = re.search(r"\{.*?\}", text, re.DOTALL)
        if m:
            try:
                data = json.loads(m.group(0))
                return {
                    "median_price": data.get("median_price"),
                    "price_band": data.get("price_band") or [],
                    "sample_count": int(data.get("sample_count") or 0),
                    "crawler_sources": data.get("crawler_sources") or [],
                }
            except Exception:
                pass
    return {"median_price": None, "price_band": [], "sample_count": 0, "crawler_sources": []}
