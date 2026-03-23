"""
상품 도메인 규칙 — 단일 진실 원천.

서비스 계층에서 중복 구현되던 규칙들을 여기서 관리.
"""
from __future__ import annotations

from typing import Any

# confidence 임계값
CONFIDENCE_THRESHOLD = 0.6


def normalize_text(value: str | None) -> str:
    """빈 문자열·의미 없는 값 정규화."""
    if not value:
        return ""
    value = str(value).strip()
    if value.lower() in {"unknown", "none", "null", "n/a"}:
        return ""
    return value


def needs_user_input(candidate: dict[str, Any]) -> bool:
    """Vision 후보의 신뢰도·필드 기준으로 사용자 입력 필요 여부 판단."""
    model = normalize_text(candidate.get("model"))
    brand = normalize_text(candidate.get("brand"))
    category = normalize_text(candidate.get("category"))
    confidence = float(candidate.get("confidence", 0.0) or 0.0)

    if not model:
        return True
    if not brand and not category:
        return True
    if confidence < CONFIDENCE_THRESHOLD:
        return True
    return False


def build_confirmed_product_from_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    """Vision 후보 → confirmed_product 표준 구조."""
    return {
        "brand": candidate.get("brand") or "",
        "model": candidate.get("model") or "",
        "category": candidate.get("category") or "",
        "confidence": float(candidate.get("confidence", 0.0) or 0.0),
        "source": candidate.get("source", "vision"),
        "storage": candidate.get("storage", "") or "",
    }


def build_confirmed_product_from_user_input(
    model: str,
    brand: str | None = None,
    category: str | None = None,
) -> dict[str, Any]:
    """사용자 직접 입력 → confirmed_product 표준 구조."""
    normalized_model = normalize_text(model)
    if not normalized_model:
        raise ValueError("모델명은 필수입니다")
    return {
        "brand": normalize_text(brand) or "Unknown",
        "model": normalized_model,
        "category": normalize_text(category) or "unknown",
        "confidence": 1.0,
        "source": "user_input",
        "storage": "",
    }
