"""
Pre-listing Clarification 노드 — 판매글 품질 향상을 위한 추가 정보 수집.

상품 확정 후, 판매글 생성 전에 실행.
상품 상태, 구성품, 거래 조건 등 판매글 품질에 필요한 정보가 부족하면
질문을 생성하고 needs_user_input 상태로 전환.
이미 답이 충분하면 바로 통과.
"""
from __future__ import annotations

from typing import Dict, List

from app.graph.seller_copilot_state import SellerCopilotState
from app.graph.nodes.helpers import _build_react_llm, _log, _record_error, _run_async


# 판매글 품질에 영향을 주는 핵심 정보 항목
LISTING_INFO_REQUIREMENTS = [
    {"id": "product_condition", "label": "상품 상태", "keywords": ["상태", "스크래치", "찍힘", "파손"]},
    {"id": "usage_period", "label": "사용 기간", "keywords": ["사용", "개월", "년", "기간"]},
    {"id": "accessories", "label": "구성품 포함 여부", "keywords": ["구성품", "충전기", "케이블", "박스", "이어폰"]},
    {"id": "delivery_method", "label": "거래 방법", "keywords": ["직거래", "택배", "배송"]},
]


def pre_listing_clarification_node(state: SellerCopilotState) -> SellerCopilotState:
    """판매글 생성 전 정보 부족 여부를 판단하고 질문을 생성한다."""
    _log(state, "pre_listing_clarification:start")

    # 이미 완료했으면 스킵
    if state.get("pre_listing_done"):
        _log(state, "pre_listing_clarification:already_done → skip")
        return state

    product = state.get("confirmed_product") or {}
    existing_answers = state.get("pre_listing_answers") or {}

    # 기존 정보에서 이미 충족된 항목 확인
    description_context = _gather_existing_info(state)
    missing = _detect_missing_info(description_context, existing_answers)

    if not missing:
        state["pre_listing_done"] = True
        state["pre_listing_questions"] = []
        _log(state, "pre_listing_clarification:all_info_sufficient → pass")
        return state

    # LLM으로 자연스러운 질문 생성 시도
    questions = _generate_questions_llm(state, product, missing)
    if not questions:
        # fallback: 룰 기반 질문 생성
        questions = _generate_questions_rule(missing)

    state["pre_listing_questions"] = questions
    state["missing_information"] = [m["id"] for m in missing]
    state["needs_user_input"] = True
    state["clarification_prompt"] = "판매글 품질을 높이기 위해 몇 가지 추가 정보가 필요합니다."

    _log(state, f"pre_listing_clarification:questions_generated count={len(questions)}")
    return state


def _gather_existing_info(state: SellerCopilotState) -> str:
    """state에서 이미 존재하는 텍스트 정보를 모은다."""
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
    """어떤 정보가 부족한지 탐지한다."""
    missing = []
    for req in LISTING_INFO_REQUIREMENTS:
        if req["id"] in existing_answers:
            continue
        if any(kw in context for kw in req["keywords"]):
            continue
        missing.append(req)
    return missing


def _generate_questions_llm(
    state: SellerCopilotState,
    product: Dict,
    missing: List[Dict],
) -> List[Dict] | None:
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

        # JSON 파싱
        import re
        content = content.strip()
        if content.startswith("```"):
            content = re.sub(r"^```(?:json)?", "", content).strip()
            content = re.sub(r"```$", "", content).strip()

        data = json.loads(content)
        if isinstance(data, list) and all(isinstance(q, dict) and "question" in q for q in data):
            return data
    except Exception as e:
        _record_error(state, "pre_listing_clarification", f"LLM question gen failed: {e}")
    return None


def _generate_questions_rule(missing: List[Dict]) -> List[Dict]:
    """룰 기반으로 질문을 생성한다."""
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
