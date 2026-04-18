"""
Clarification — Single Tool Node (PR3 통합).

분류 (Target Architecture, 4+2+5):
  clarification_node → Single Tool Node (with deterministic fallback)
                       사용자에게 추가 정보를 요청. selection 없음.

통합 배경:
  PR3 이전: 두 개의 분리된 노드
    - product_agent.py:clarification_node            — Vision confidence 낮을 때 모델명 직접 입력 대기
    - clarification_listing_agent.py:pre_listing_clarification_node — 판매글 품질용 추가 정보 LLM 질문

  PR3 이후: 단일 entry point clarification_node(state)
    - 같은 책임 (사용자에게 정보 요청)이라 통합
    - state.confirmed_product 유무로 모드 자동 결정
    - planner의 clarification_policy(ask_early/ask_late)로 적극성 조절

clarification_policy 동작:
  ask_early: missing_info 있으면 즉시 질문 (현재 동작 유지, baseline)
  ask_late:  pre_listing 단계에서 미정보를 자동 진행 (속도 우선, shallow + 정보 풍부 케이스)
             단, product 식별 단계는 confidence가 너무 낮으면 무조건 질문 (안전)

기존 함수명은 PR3에서 알리아스로 유지 (PR4-cleanup에서 graph builder 갱신 후 제거).
"""
from __future__ import annotations

from typing import Dict, List, Optional

import logging

from app.graph.seller_copilot_state import SellerCopilotState
from app.graph.nodes.helpers import _build_react_llm, _log, _record_error, _run_async


# 판매글 품질에 영향을 주는 핵심 정보 항목
_LISTING_INFO_REQUIREMENTS = [
    {"id": "product_condition", "label": "상품 상태", "keywords": ["상태", "스크래치", "찍힘", "파손"]},
    {"id": "usage_period", "label": "사용 기간", "keywords": ["사용", "개월", "년", "기간"]},
    {"id": "accessories", "label": "구성품 포함 여부", "keywords": ["구성품", "충전기", "케이블", "박스", "이어폰"]},
    {"id": "delivery_method", "label": "거래 방법", "keywords": ["직거래", "택배", "배송"]},
]


def clarification_node(state: SellerCopilotState) -> SellerCopilotState:
    """단일 통합 entry point. state로 모드 자동 분기.

    모드 결정:
      - confirmed_product 없음/약함 → product 모드 (모델명 직접 입력 대기, LLM 호출 없음)
      - confirmed_product 있음 + pre_listing_done=False → pre_listing 모드 (LLM 질문 생성)
      - 그 외 → no-op
    """
    product = state.get("confirmed_product") or {}
    needs_input = state.get("needs_user_input", False)

    # 모드 1: product 식별 단계 (LLM 안 씀, 단순 대기)
    # needs_user_input=True 이면서 confirmed_product 없거나 confidence 낮음 → product 모드
    if needs_input and (not product or float(product.get("confidence", 0) or 0) < 0.6):
        return _wait_for_product_input(state)

    # 모드 2: pre_listing 품질 향상용 추가 정보
    if not state.get("pre_listing_done", False):
        return _generate_pre_listing_questions(state)

    # 모드 3: 이미 완료 상태 → no-op
    _log(state, "clarification:already_done → noop")
    return state


# ── 모드 1: product 모드 ─────────────────────────────────────────────


def _wait_for_product_input(state: SellerCopilotState) -> SellerCopilotState:
    """Vision confidence 낮음 → 사용자 입력 대기 (LLM 호출 없음).

    product_agent.clarification_node와 동일 동작.
    """
    _log(state, "clarification:product_mode:waiting_for_user_input")
    state["checkpoint"] = "A_needs_user_input"
    state["status"] = "awaiting_product_confirmation"
    return state


# ── 모드 2: pre_listing 모드 ─────────────────────────────────────────


def _generate_pre_listing_questions(state: SellerCopilotState) -> SellerCopilotState:
    """판매글 품질용 추가 정보 질문 생성. clarification_policy로 적극성 조절."""
    _log(state, "clarification:pre_listing_mode:start")

    product = state.get("confirmed_product") or {}
    existing_answers = state.get("pre_listing_answers") or {}

    description_context = _gather_existing_info(state)
    missing = _detect_missing_info(description_context, existing_answers)

    if not missing:
        state["pre_listing_done"] = True
        state["pre_listing_questions"] = []
        _log(state, "clarification:pre_listing:all_info_sufficient → pass")
        return state

    # ── PR3: clarification_policy로 적극성 조절 ─────────────────
    policy = state.get("clarification_policy", "ask_early")
    if policy == "ask_late":
        # 정보 부족이라도 자동으로 진행 (사용자에게 묻지 않음). pre_listing_done=True.
        state["pre_listing_done"] = True
        state["pre_listing_questions"] = []
        state["missing_information"] = [m["id"] for m in missing]
        state.setdefault("debug_logs", []).append(
            f"clarification:ask_late:auto_proceed_with_missing={[m['id'] for m in missing]}"
        )
        _log(state, f"clarification:pre_listing:ask_late skip_questions count={len(missing)}")
        return state

    # ask_early — 질문 생성
    questions = _generate_questions_llm(state, product, missing)
    if not questions:
        questions = _generate_questions_rule(missing)

    state["pre_listing_questions"] = questions
    state["missing_information"] = [m["id"] for m in missing]
    state["needs_user_input"] = True
    state["clarification_prompt"] = "판매글 품질을 높이기 위해 몇 가지 추가 정보가 필요합니다."
    state["checkpoint"] = "A_needs_user_input"

    _log(state, f"clarification:pre_listing:questions_generated count={len(questions)}")
    return state


def _gather_existing_info(state: SellerCopilotState) -> str:
    parts = []
    product = state.get("confirmed_product") or {}
    parts.append(str(product))

    user_input = state.get("user_product_input") or {}
    if user_input:
        parts.append(str(user_input))

    answers = state.get("pre_listing_answers") or {}
    for v in answers.values():
        parts.append(str(v))

    return " ".join(parts).lower()


def _detect_missing_info(context: str, existing_answers: Dict) -> List[Dict]:
    missing = []
    for req in _LISTING_INFO_REQUIREMENTS:
        if req["id"] in existing_answers:
            continue
        if any(kw in context for kw in req["keywords"]):
            continue
        missing.append(req)
    return missing


def _generate_questions_llm(
    state: SellerCopilotState, product: Dict, missing: List[Dict],
) -> Optional[List[Dict]]:
    """LLM으로 자연스러운 질문을 생성한다."""
    try:
        llm = _build_react_llm()
        if llm is None:
            return None

        missing_labels = ", ".join(m["label"] for m in missing)
        prompt = f"""당신은 중고거래 판매글 작성을 도와주는 어시스턴트입니다.
아래 상품에 대해 판매글 품질을 높이기 위한 추가 질문을 생성하세요.

상품: {product.get('brand', '')} {product.get('model', '')}
부족한 정보: {missing_labels}

반드시 JSON 배열로만 응답:
[{{"id": "info_id", "question": "사용자에게 할 질문"}}]

규칙:
- 친근하고 자연스러운 한국어로
- 각 질문은 간결하게 1문장
- 부족한 정보 항목마다 1개씩"""

        import json
        from langchain_core.messages import HumanMessage
        result = _run_async(lambda: llm.ainvoke([HumanMessage(content=prompt)]))
        content = result.content if hasattr(result, "content") else str(result)

        import re
        content = content.strip()
        if content.startswith("```"):
            content = re.sub(r"^```(?:json)?", "", content).strip()
            content = re.sub(r"```$", "", content).strip()

        data = json.loads(content)
        if isinstance(data, list) and all(isinstance(q, dict) and "question" in q for q in data):
            return data
    except Exception as e:
        logging.getLogger(__name__).error("clarification LLM failed", exc_info=True)
        _record_error(state, "clarification", f"LLM question gen failed: {e}")
    return None


def _generate_questions_rule(missing: List[Dict]) -> List[Dict]:
    """룰 기반 질문 생성 (LLM fallback)."""
    question_templates = {
        "product_condition": "상품 상태는 어떤가요? (스크래치, 찍힘 등)",
        "usage_period": "사용 기간이 어느 정도 되나요?",
        "accessories": "구성품(박스, 충전기 등)이 포함되나요?",
        "delivery_method": "직거래와 택배 중 어떤 방식을 선호하시나요?",
    }
    return [
        {"id": m["id"], "question": question_templates.get(m["id"], f"{m['label']}에 대해 알려주세요.")}
        for m in missing
    ]
