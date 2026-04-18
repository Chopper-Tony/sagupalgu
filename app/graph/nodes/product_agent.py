"""
Agent 1 — Product Identity (PR4-2: Tool Agent로 승격)

분류 (Target Architecture, 4+2+5 → PR4 후 4 + 1 = 5 에이전트):
  product_identity_agent  → Tool Agent (ReAct)
                            LLM이 신규 툴 3개 (lc_image_reanalyze_tool /
                            lc_rag_product_catalog_tool / lc_ask_user_clarification_tool)
                            중 자율 선택해 confidence·정보 보강.

호환성:
  - 그래프 빌더에 등록된 노드 이름은 'product_identity_node' 유지 (외부 안정).
  - 함수 이름은 product_identity_agent (정식). product_identity_node·product_gate_node는
    호환 alias (PR1~3 패턴, post-PR5에 정리 검토).

Fallback 정책 (LLM 실패 시 PR4-cleanup의 deterministic 로직 100% 보존):
  1. enable_product_identity_agent=False → 즉시 _deterministic_fallback
  2. _build_react_llm() 실패 → _deterministic_fallback + record_error
  3. agent.ainvoke 예외 → _deterministic_fallback + record_error
  4. 응답 파싱 실패 → _deterministic_fallback + failure_mode='product_identity_parse_error'
  5. 필수 필드 누락 → _deterministic_fallback + failure_mode='product_identity_contract_violation'

예산 가드:
  - state["product_identity_tool_calls"]에 호출 카운트 누적
  - reanalyze 2회 / clarify 1회 한도 (tool 자체 + system_prompt 양쪽)
  - ReAct max_iterations=5
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

from app.graph.seller_copilot_state import ConfirmedProduct, SellerCopilotState
from app.graph.nodes.helpers import _log, _record_error, _record_tool_call, _run_async

logger = logging.getLogger(__name__)


# ── 메인 entry ─────────────────────────────────────────────────────────


def product_identity_agent(state: SellerCopilotState) -> SellerCopilotState:
    """Tool Agent. Vision 결과·후보를 보고 LLM이 자율 보강 또는 deterministic fallback."""
    _log(state, "agent1:product_identity:start")

    from app.core.config import get_settings

    settings = get_settings()
    if not getattr(settings, "enable_product_identity_agent", False):
        _log(state, "agent1:flag_off → deterministic_fallback")
        return _deterministic_fallback(state)

    # 사용자가 직접 입력한 경우는 ReAct 불필요 (가장 강한 신호) — 바로 확정
    user_input = state.get("user_product_input") or {}
    if user_input and user_input.get("model"):
        _log(state, "agent1:user_input → skip ReAct")
        return _confirm_from_user_input(state, user_input)

    # ReAct 실행
    try:
        result = _run_react(state)
        if result is None:
            _log(state, "agent1:react returned None → deterministic_fallback")
            return _deterministic_fallback(state)
        applied = _apply_react_result(state, result)
        # CTO PR4-2 #6: A/B 비교 로그 (agent vs deterministic confidence delta)
        _log_quality_comparison(state, applied)
        # CTO PR4-2 #2: observability hook
        _emit_observability_metrics(state, applied)
        return applied
    except Exception as e:
        logger.error("agent1 ReAct failed", exc_info=True)
        _record_error(state, "product_identity_agent", f"ReAct failed: {e}")
        _log(state, f"agent1:react_exception → deterministic_fallback error={e}")
        state["product_identity_failure_mode"] = "react_exception"
        result = _deterministic_fallback(state)
        _emit_observability_metrics(state, result)
        return result


# ── ReAct 실행 ─────────────────────────────────────────────────────────


def _run_react(state: SellerCopilotState) -> Optional[Dict[str, Any]]:
    """LLM이 신규 툴 3개로 confidence 보강. 최종 응답 dict 반환 또는 None."""
    from app.tools.agentic_tools import (
        lc_ask_user_clarification_tool,
        lc_image_reanalyze_tool,
        lc_rag_product_catalog_tool,
    )
    from app.graph.nodes.helpers import _build_react_llm

    llm = _build_react_llm()
    if llm is None:
        return None

    from langchain_core.messages import HumanMessage
    from langchain.agents import create_agent

    candidates = state.get("product_candidates") or []
    image_paths = state.get("image_paths") or []
    user_input = state.get("user_product_input") or {}
    category_hint = (user_input.get("category") or "").strip()

    system_prompt = _build_system_prompt()
    user_prompt = _build_user_prompt(candidates, image_paths, category_hint)

    agent = create_agent(
        llm,
        [lc_image_reanalyze_tool, lc_rag_product_catalog_tool, lc_ask_user_clarification_tool],
        system_prompt=system_prompt,
    )

    _log(state, "agent1:react:invoking max_iterations=5")
    msgs = [HumanMessage(content=user_prompt)]
    react_result = _run_async(lambda: agent.ainvoke({"messages": msgs}, config={"recursion_limit": 12}))

    # tool_calls 누적 + 노드 trace 기록
    tool_calls_seq = state.get("product_identity_tool_calls") or []
    for msg in react_result.get("messages", []):
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            for tc in msg.tool_calls:
                name = tc.get("name") or ""
                if name:
                    tool_calls_seq.append(name)
                    _log(state, f"agent1:llm_tool:{name}")
                    _record_tool_call(state, {
                        "tool_name": name, "input": tc.get("args", {}),
                        "output": None, "success": True,
                    })
    state["product_identity_tool_calls"] = tool_calls_seq

    # PR4-3: catalog tool 응답에서 cold_start 신호 추출 → metric 용
    state["product_identity_catalog_cold_start"] = _extract_catalog_cold_start(react_result)

    # 마지막 message → 최종 JSON 응답
    final_content = ""
    if react_result.get("messages"):
        final_content = str(react_result["messages"][-1].content or "")

    parsed = _parse_final_response(final_content)
    if parsed is None:
        _record_error(state, "product_identity_agent", f"final response parse failed: {final_content[:120]}")
        state["product_identity_failure_mode"] = "product_identity_parse_error"
        return None

    return parsed


# ── 응답 적용 ───────────────────────────────────────────────────────────


def _apply_react_result(state: SellerCopilotState, result: Dict[str, Any]) -> SellerCopilotState:
    """파싱된 ReAct 응답을 state에 반영. 추가 deterministic 가드 적용."""
    from app.tools.product_identity_tools import total_budget_exceeded

    confirmed = result.get("confirmed_product") or {}
    needs_input = bool(result.get("needs_user_input", False))
    rationale = result.get("rationale", "")

    tool_calls_seq = state.get("product_identity_tool_calls") or []
    confidence = float(confirmed.get("confidence", 0.0) or 0.0)

    # CTO PR4-2 #1: total tool calls soft budget 초과 시 강제 종료
    if total_budget_exceeded(tool_calls_seq):
        _log(state, f"agent1:total_budget_exceeded count={len(tool_calls_seq)} → fallback")
        state["product_identity_failure_mode"] = "react_total_budget_exceeded"
        return _deterministic_fallback(state)

    # 필수 필드 검증
    if not needs_input and not confirmed.get("model"):
        _log(state, "agent1:contract_violation: needs_user_input=False but model missing")
        state["product_identity_failure_mode"] = "product_identity_contract_violation"
        return _deterministic_fallback(state)

    # CTO PR4-2 #4: clarify explicit heuristic
    # LLM이 confirmed로 응답했더라도 deterministic 안전망:
    #   confidence < 0.5 AND reanalyze 2회 모두 소진 → 강제 clarify
    #   (LLM에 맡기면 흔들리는 영역이라 결정론적 가드)
    reanalyze_done = tool_calls_seq.count("lc_image_reanalyze_tool")
    if not needs_input and confidence < 0.5 and reanalyze_done >= 2:
        _log(state, f"agent1:clarify_forced confidence={confidence:.2f} reanalyze={reanalyze_done}")
        state["product_identity_failure_mode"] = "clarify_forced_by_heuristic"
        state["needs_user_input"] = True
        state["clarification_prompt"] = (
            "여러 번 시도했지만 사진만으로 정확히 식별하지 못했습니다. "
            "모델명을 직접 입력해 주세요."
        )
        state["checkpoint"] = "A_needs_user_input"
        state["status"] = "awaiting_product_confirmation"
        return state

    if needs_input:
        # clarify 요청
        questions = result.get("clarification_questions") or []
        clarification_prompt = result.get("clarification_prompt") or (
            "상품 식별을 위해 추가 정보가 필요합니다."
        )
        state["needs_user_input"] = True
        state["clarification_prompt"] = clarification_prompt
        if questions:
            state["pre_listing_questions"] = questions
        state["checkpoint"] = "A_needs_user_input"
        state["status"] = "awaiting_product_confirmation"
        _log(state, f"agent1:react:clarify rationale={rationale[:80]}")
        return state

    # 확정
    state["confirmed_product"] = ConfirmedProduct(
        brand=str(confirmed.get("brand", "")),
        model=str(confirmed.get("model", "")),
        category=str(confirmed.get("category", "")),
        confidence=float(confirmed.get("confidence", 0.7) or 0.7),
        source=str(confirmed.get("source", "react")),
        storage=str(confirmed.get("storage", "")),
    )
    state["needs_user_input"] = False
    state["clarification_prompt"] = None
    state["checkpoint"] = "A_complete"
    state["status"] = "product_confirmed"
    _log(state, f"agent1:react:confirmed source={confirmed.get('source')} rationale={rationale[:80]}")
    return state


def _parse_final_response(content: str) -> Optional[Dict[str, Any]]:
    """LLM 마지막 message에서 JSON 추출."""
    content = content.strip()
    if content.startswith("```"):
        content = re.sub(r"^```(?:json)?", "", content).strip()
        content = re.sub(r"```$", "", content).strip()
    try:
        data = json.loads(content)
        if isinstance(data, dict):
            return data
    except (json.JSONDecodeError, ValueError, TypeError):
        pass
    m = re.search(r"\{.*\}", content, re.DOTALL)
    if m:
        try:
            data = json.loads(m.group(0))
            if isinstance(data, dict):
                return data
        except (json.JSONDecodeError, ValueError, TypeError):
            pass
    return None


# ── 프롬프트 ──────────────────────────────────────────────────────────


def _build_system_prompt() -> str:
    return """당신은 중고거래 상품 식별 에이전트다. Vision이 산출한 후보의 confidence와 정보 완결성을 평가하고 필요 시 도구를 호출하라.

도구 사용 가이드:
- lc_image_reanalyze_tool(focus="ocr"|"spec"|"category_hint"): Vision 재분석. 한 세션에서 *최대 2회*.
- lc_rag_product_catalog_tool(brand_hint, model_hint, category_hint): 사구팔구 sold + 외부 시세 카탈로그 RAG.
- lc_ask_user_clarification_tool(questions_json, reason): 사용자에게 질문. 한 세션에서 *최대 1회*.

의사결정 가이드:
- confidence >= 0.8 AND brand/model 모두 있음 → 도구 호출 0, 바로 confirmed JSON 반환.
- 0.5 <= confidence < 0.8 또는 brand 누락 → lc_rag_product_catalog_tool 먼저. top_match_confidence >= 0.7이면 그 매칭으로 확정.
- confidence < 0.5 → lc_image_reanalyze_tool (focus='ocr' 또는 'spec'). 두 번 재분석해도 < 0.5면 lc_ask_user_clarification_tool로 질문.
- candidates 비어있음 → 바로 lc_ask_user_clarification_tool.
- catalog가 cold_start=true면 catalog 결과 신뢰도 낮게 평가하고 clarify로 분기.

예산 (절대 어기지 말 것):
- lc_image_reanalyze_tool: 최대 2회. 초과 시 도구가 'reanalyze_budget_exceeded' 반환 → clarify로 선회.
- lc_ask_user_clarification_tool: 최대 1회. 이미 호출했으면 fallback JSON 반환.

최종 응답 형식 (JSON만, 설명 없이):
{
  "confirmed_product": {"brand": "", "model": "", "category": "", "confidence": 0.0, "source": "vision|catalog|reanalyzed|user_input"},
  "needs_user_input": false,
  "clarification_prompt": "사용자에게 보여줄 메시지 (needs_user_input=true일 때만)",
  "clarification_questions": [{"id": "...", "question": "..."}],
  "rationale": "어떤 도구를 왜 호출했는지 한 줄"
}"""


def _build_user_prompt(candidates: List[Dict], image_paths: List[str], category_hint: str) -> str:
    candidates_summary = json.dumps(candidates[:3], ensure_ascii=False) if candidates else "[]"
    return f"""현재 상황:
- 이미지: {len(image_paths)}장
- Vision 후보 (top 3): {candidates_summary}
- 사용자 카테고리 힌트: {category_hint or '(없음)'}
- 이미지 경로 JSON (도구 입력용): {json.dumps(image_paths, ensure_ascii=False)}

위 정보를 기반으로 의사결정해서 최종 JSON을 반환하라."""


# ── Quality 비교 + Observability (CTO PR4-2 #2, #6) ──────────────────


def _log_quality_comparison(state: SellerCopilotState, agent_result: SellerCopilotState) -> None:
    """CTO PR4-2 #6: agent vs deterministic 결과 confidence delta 로깅.

    full A/B 비교 (양쪽 동시 실행)는 비용 2배라 회피.
    대신 agent 결과의 confidence를 deterministic이 산출했을 confidence와 비교 가능하게
    상위 candidate confidence를 함께 기록한다. 후속 분석으로 quality regression 감지.
    """
    candidates = state.get("product_candidates") or []
    deterministic_top = float(candidates[0].get("confidence", 0.0) or 0.0) if candidates else 0.0
    agent_confirmed = (agent_result.get("confirmed_product") or {})
    agent_conf = float(agent_confirmed.get("confidence", 0.0) or 0.0)
    delta = agent_conf - deterministic_top
    _log(
        state,
        f"agent1:quality_compare deterministic_top={deterministic_top:.2f} "
        f"agent={agent_conf:.2f} delta={delta:+.2f} source={agent_confirmed.get('source')}"
    )


def _extract_catalog_cold_start(react_result: Dict[str, Any]) -> bool:
    """react_result.messages 에서 lc_rag_product_catalog_tool 의 ToolMessage 응답을 찾아
    cold_start=true 였는지 판정. PR4-3 observability 용.

    catalog tool 호출이 없었으면 False (cold_start 라는 신호 자체가 없음).
    contract 위반 응답 (cold_start 필드 누락 등) 도 False — 다만 logger.warning 으로
    drift 감지 가능하게 남김 (CTO PR4-3 #3: tool response schema 명시 필드 강제).
    """
    from app.tools.product_identity_tools import validate_catalog_tool_response

    for msg in react_result.get("messages", []):
        name = getattr(msg, "name", "") or ""
        if name != "lc_rag_product_catalog_tool":
            continue
        content = getattr(msg, "content", "") or ""
        if not isinstance(content, str):
            continue
        try:
            payload = json.loads(content)
        except (json.JSONDecodeError, ValueError, TypeError):
            logger.warning("[catalog_contract] non-json ToolMessage content")
            continue
        if not validate_catalog_tool_response(payload):
            keys = list(payload.keys()) if isinstance(payload, dict) else type(payload).__name__
            logger.warning(f"[catalog_contract] response missing cold_start field: keys={keys}")
            continue
        if payload.get("cold_start") is True:
            return True
    return False


def _emit_observability_metrics(state: SellerCopilotState, result: SellerCopilotState) -> None:
    """CTO PR4-2 #2: tool usage / fallback / clarify 비율 metric hook.
    PR4-3: app.middleware.metrics 의 in-process 카운터로 누적 + 구조화 로그.
    """
    from app.middleware.metrics import emit_product_identity_run

    tool_calls_seq = result.get("product_identity_tool_calls") or []
    failure_mode = result.get("product_identity_failure_mode")
    needs_input = bool(result.get("needs_user_input"))
    confirmed_source = (result.get("confirmed_product") or {}).get("source", "")

    emit_product_identity_run(
        tool_calls_total=len(tool_calls_seq),
        reanalyze_count=tool_calls_seq.count("lc_image_reanalyze_tool"),
        catalog_count=tool_calls_seq.count("lc_rag_product_catalog_tool"),
        clarify_count=tool_calls_seq.count("lc_ask_user_clarification_tool"),
        failure_mode=failure_mode,
        needs_user_input=needs_input,
        confirmed_source=confirmed_source,
        cold_start=bool(result.get("product_identity_catalog_cold_start", False)),
    )


# ── Deterministic Fallback (PR4-cleanup의 product_gate 로직 100% 복원) ─


def _deterministic_fallback(state: SellerCopilotState) -> SellerCopilotState:
    """LLM 사용 불가·실패 시 PR4-cleanup의 product_gate_node 로직 그대로 실행."""
    _log(state, "agent1:deterministic_fallback:start")

    user_input = state.get("user_product_input") or {}
    candidates = state.get("product_candidates") or []

    # 경로 A: 사용자 직접 입력
    if user_input and user_input.get("model"):
        return _confirm_from_user_input(state, user_input)

    # 경로 B: Vision 결과
    if candidates:
        best = candidates[0]
        confidence = float(best.get("confidence", 0.0) or 0.0)
        model = (best.get("model") or "").strip().lower()
        if confidence < 0.6 or model in {"unknown", ""}:
            state["needs_user_input"] = True
            state["clarification_prompt"] = (
                "사진만으로 모델명을 정확히 식별하지 못했습니다. "
                "모델명을 직접 입력해 주세요."
            )
            state["checkpoint"] = "A_needs_user_input"
            state["status"] = "awaiting_product_confirmation"
            _log(state, f"agent1:fallback:low_confidence={confidence:.2f}")
            return state

        confirmed = ConfirmedProduct(
            brand=best.get("brand", ""),
            model=best.get("model", ""),
            category=best.get("category", ""),
            confidence=confidence,
            source=best.get("source", "vision"),
            storage=best.get("storage", ""),
        )
        state["confirmed_product"] = confirmed
        state["needs_user_input"] = False
        state["clarification_prompt"] = None
        state["checkpoint"] = "A_complete"
        state["status"] = "product_confirmed"
        _log(state, f"agent1:fallback:vision_confirmed confidence={confidence:.2f}")
        return state

    # 경로 C: candidates 없음
    state["needs_user_input"] = True
    state["clarification_prompt"] = (
        "상품 정보를 파악하지 못했습니다. "
        "모델명을 직접 입력해주시거나 사진을 다시 업로드해주세요."
    )
    state["checkpoint"] = "A_needs_user_input"
    state["status"] = "awaiting_product_confirmation"
    _log(state, "agent1:fallback:no_candidates")
    return state


def _confirm_from_user_input(state: SellerCopilotState, user_input: Dict[str, Any]) -> SellerCopilotState:
    """사용자 직접 입력 → 즉시 confidence=1.0 확정."""
    confirmed = ConfirmedProduct(
        brand=user_input.get("brand", ""),
        model=user_input.get("model", ""),
        category=user_input.get("category", ""),
        confidence=1.0,
        source="user_input",
        storage=user_input.get("storage", ""),
    )
    state["confirmed_product"] = confirmed
    state["needs_user_input"] = False
    state["clarification_prompt"] = None
    state["checkpoint"] = "A_complete"
    state["status"] = "product_confirmed"
    _log(state, "agent1:user_input_confirmed")
    return state


# ── 호환 alias (PR1~3 패턴) ──────────────────────────────────────────
# 그래프 빌더가 product_identity_node로 등록 → product_identity_agent 호출.
# product_gate_node는 PR1 alias 잔재로 호환 유지 (post-PR5 cleanup 검토).
product_identity_node = product_identity_agent
product_gate_node = product_identity_agent
