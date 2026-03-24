"""
세션 상품 데이터 조작 — 순수 함수 집합.

SessionService에서 상품 관련 product_data 조작 로직을 분리.
session_meta.py(workflow_meta 조작)와 동일한 패턴.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.domain.product_rules import needs_user_input, normalize_text


def attach_image_paths(product_data: Dict, image_urls: List[str]) -> Dict:
    """이미지 URL을 product_data에 기록한다."""
    product_data["image_paths"] = image_urls
    return product_data


def apply_analysis_result(
    product_data: Dict,
    candidates: List[Dict[str, Any]],
    image_paths: List[str],
) -> tuple[Dict, bool]:
    """Vision AI 분석 결과를 product_data에 반영한다.

    Returns:
        (product_data, needs_input) 튜플.
    """
    if not candidates:
        raise ValueError("상품 인식 결과가 없습니다")

    top = candidates[0]
    needs_input = needs_user_input(top)

    product_data["candidates"] = candidates
    product_data["analysis_source"] = "vision"
    product_data["image_count"] = len(image_paths)
    product_data["needs_user_input"] = needs_input

    if needs_input:
        product_data["user_input_prompt"] = (
            "사진만으로 모델명을 정확히 식별하지 못했습니다. 모델명을 직접 입력해 주세요."
        )
    else:
        product_data.pop("user_input_prompt", None)

    return product_data, needs_input


def confirm_from_candidate(
    product_data: Dict,
    candidate_index: int,
) -> Dict:
    """후보 목록에서 선택하여 상품을 확정한다."""
    candidates = product_data.get("candidates") or []
    if not (0 <= candidate_index < len(candidates)):
        raise ValueError("유효하지 않은 후보 인덱스입니다")

    product_data["confirmed_product"] = {**candidates[candidate_index], "source": "vision"}
    product_data["needs_user_input"] = False
    product_data.pop("user_input_prompt", None)
    return product_data


def confirm_from_user_input(
    product_data: Dict,
    model: str,
    brand: Optional[str] = None,
    category: Optional[str] = None,
) -> Dict:
    """사용자 직접 입력으로 상품을 확정한다."""
    normalized_model = normalize_text(model)
    if not normalized_model:
        raise ValueError("모델명은 필수입니다")

    product_data["confirmed_product"] = {
        "brand": normalize_text(brand) or "Unknown",
        "model": normalized_model,
        "category": normalize_text(category) or "unknown",
        "confidence": 1.0,
        "source": "user_input",
    }
    product_data["needs_user_input"] = False
    product_data.pop("user_input_prompt", None)
    return product_data
