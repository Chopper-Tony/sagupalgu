"""
Agent 4 (검증) — 판매글 품질 검사

노드:
  validation_node  — listing 필수 필드·가격·길이 검사
"""
from __future__ import annotations

from typing import List

from app.graph.seller_copilot_state import SellerCopilotState, ValidationIssue, ValidationResult
from app.graph.nodes.helpers import _log, _safe_int


def validation_node(state: SellerCopilotState) -> SellerCopilotState:
    _log(state, "agent4:validation:start")

    issues: List[ValidationIssue] = []
    canonical = state.get("canonical_listing") or {}
    product = state.get("confirmed_product") or {}
    market_context = state.get("market_context") or {}

    if not product.get("model"):
        issues.append(ValidationIssue(code="missing_model", message="상품 모델명 없음", severity="error"))

    title = (canonical.get("title") or "").strip()
    if len(title) < 5:
        issues.append(ValidationIssue(code="title_too_short", message="제목이 너무 짧습니다", severity="error"))

    description = (canonical.get("description") or "").strip()
    if len(description) < 20:
        issues.append(ValidationIssue(code="description_too_short", message="설명이 너무 짧습니다", severity="error"))

    price = _safe_int(canonical.get("price"), 0)
    if price <= 0:
        issues.append(ValidationIssue(code="invalid_price", message="가격이 유효하지 않습니다", severity="error"))

    sample_count = _safe_int(market_context.get("sample_count"), 0)
    if sample_count == 0:
        issues.append(ValidationIssue(code="no_market_data", message="시장 데이터 없음", severity="warning"))

    passed = not any(i["severity"] == "error" for i in issues)
    state["validation_passed"] = passed
    state["validation_result"] = ValidationResult(passed=passed, issues=issues)

    if passed:
        state["checkpoint"] = "B_complete"
    else:
        retry = _safe_int(state.get("validation_retry_count"), 0)
        state["validation_retry_count"] = retry + 1
        state["checkpoint"] = "B_validation_failed"

    _log(state, f"agent4:validation:passed={passed} issues={len(issues)} retry={state.get('validation_retry_count')}")
    return state
