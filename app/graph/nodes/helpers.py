"""
노드 공통 헬퍼 — 로깅, tool_call 기록, async 실행, LLM 초기화
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict

from app.graph.seller_copilot_state import SellerCopilotState


def _log(state: SellerCopilotState, msg: str) -> None:
    logs = state.get("debug_logs") or []
    logs.append(f"[{datetime.now(timezone.utc).isoformat()}] {msg}")
    state["debug_logs"] = logs


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


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _run_async(coro_or_factory):
    """동기 컨텍스트에서 async 도구 실행.

    callable(lambda)이 전달되면 호출해서 코루틴을 생성한다.
    이를 통해 테스트에서 _run_async를 mock할 때 코루틴이 미리 생성되지 않아
    'coroutine never awaited' RuntimeWarning을 방지한다.
    """
    import inspect
    coro = coro_or_factory() if callable(coro_or_factory) and not inspect.iscoroutine(coro_or_factory) else coro_or_factory
    try:
        asyncio.get_running_loop()
        # 이미 실행 중인 루프가 있으면 별도 스레드에서 실행
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            future = pool.submit(asyncio.run, coro)
            return future.result()
    except RuntimeError:
        # 실행 중인 루프 없음 — 직접 실행
        return asyncio.run(coro)


def _build_react_llm():
    """ReAct 에이전트용 LLM 초기화 (bind_tools 지원 모델)"""
    from app.core.config import settings
    try:
        if settings.gemini_api_key:
            from langchain_google_genai import ChatGoogleGenerativeAI
            return ChatGoogleGenerativeAI(
                model=settings.gemini_listing_model,
                google_api_key=settings.gemini_api_key,
                temperature=0.0,
            )
    except Exception:
        pass
    try:
        if settings.openai_api_key:
            from langchain_openai import ChatOpenAI
            return ChatOpenAI(
                model=settings.openai_listing_model,
                api_key=settings.openai_api_key,
                temperature=0.0,
            )
    except Exception:
        pass
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
