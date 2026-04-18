"""
Agent 4 (검증) — 판매글 품질 검사

분류 (Target Architecture, 4+2+5):
  validation_rules_node  → Deterministic Node
                           listing 필수 필드·가격·길이 검사. LLM 호출 없음.
                           PR2에서 copywriting_agent.refinement_node의 보강 로직 흡수:
                             - description 짧음 → 자동 텍스트 보강
                             - price 0원 → market_context·strategy 기반 자동 산정
                           보강 가능 시 보강 후 재검증 → pass 처리.
                           보강 불가 시 repair_action_hint 남김 (다음 critic이 참조).
"""
from __future__ import annotations

from typing import Dict, List

from app.graph.seller_copilot_state import SellerCopilotState, ValidationIssue, ValidationResult
from app.graph.nodes.helpers import _log, _safe_int


MAX_AUTO_PATCH_ATTEMPTS = 1  # 보강은 한 번만 시도 (무한 루프 차단)


def validation_rules_node(state: SellerCopilotState) -> SellerCopilotState:
    """필드·가격·길이 검사 + 자동 보강 + 재검증 (deterministic)."""
    _log(state, "agent4:validation_rules:start")

    canonical = dict(state.get("canonical_listing") or {})
    product = state.get("confirmed_product") or {}
    market_context = state.get("market_context") or {}
    strategy = state.get("strategy") or {}

    issues = _check(canonical, product, market_context)
    passed = _no_errors(issues)

    if passed:
        _finalize(state, canonical, issues, passed=True)
        _log(state, f"agent4:validation_rules:passed=True issues={len(issues)}")
        return state

    # ── PR2 흡수: 자동 보강 (구 refinement_node 로직) ──────────────
    if _is_auto_patchable(issues) and int(state.get("validation_retry_count") or 0) < MAX_AUTO_PATCH_ATTEMPTS:
        _log(state, "agent4:validation_rules:auto_patch:attempt")
        canonical = _auto_patch(canonical, market_context, strategy)
        # 재검증
        issues = _check(canonical, product, market_context)
        passed = _no_errors(issues)
        state["validation_retry_count"] = int(state.get("validation_retry_count") or 0) + 1
        _log(state, f"agent4:validation_rules:auto_patch:done passed={passed} issues={len(issues)}")

    if passed:
        _finalize(state, canonical, issues, passed=True)
        return state

    # 보강 불가 또는 보강 후에도 실패 → repair_action_hint (다음 critic 참조용)
    _finalize(state, canonical, issues, passed=False)
    state["repair_action_hint"] = _suggest_repair_hint(issues)
    state.setdefault("debug_logs", []).append(
        f"validation:fail_after_patch repair_action_hint={state['repair_action_hint']}"
    )
    _log(state, f"agent4:validation_rules:passed=False issues={len(issues)} hint={state['repair_action_hint']}")
    return state


# ── 검증 ──────────────────────────────────────────────────────────────


def _check(canonical: Dict, product: Dict, market_context: Dict) -> List[ValidationIssue]:
    issues: List[ValidationIssue] = []

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

    return issues


def _no_errors(issues: List[ValidationIssue]) -> bool:
    return not any(i.get("severity") == "error" for i in issues)


# ── 자동 보강 (구 refinement_node 로직 흡수) ──────────────────────────

# title/model 누락 같은 항목은 보강 불가 → critic이 rewrite_title/clarify/replan 결정.
_AUTO_PATCHABLE_CODES = {"description_too_short", "invalid_price"}


def _is_auto_patchable(issues: List[ValidationIssue]) -> bool:
    error_codes = {i.get("code") for i in issues if i.get("severity") == "error"}
    if not error_codes:
        return False
    return error_codes.issubset(_AUTO_PATCHABLE_CODES)


def _auto_patch(canonical: Dict, market_context: Dict, strategy: Dict) -> Dict:
    """description 짧음 + price 0원 한정 결정론적 보강."""
    description = (canonical.get("description") or "").strip()
    if len(description) < 20:
        canonical["description"] = (
            description + "\n제품 상태는 실사진을 참고해 주세요. 빠른 거래 원합니다."
        ).strip()

    price = _safe_int(canonical.get("price"), 0)
    if price <= 0:
        median = _safe_int(market_context.get("median_price"), 0)
        recommended = _safe_int(strategy.get("recommended_price"), 0)
        canonical["price"] = recommended or (int(median * 0.97) if median > 0 else 0)

    return canonical


def _suggest_repair_hint(issues: List[ValidationIssue]) -> str:
    """보강 불가 시 critic이 참조할 repair_action 힌트."""
    error_codes = {i.get("code") for i in issues if i.get("severity") == "error"}
    if "missing_model" in error_codes:
        return "clarify"
    if "title_too_short" in error_codes:
        return "rewrite_title"
    return "rewrite_full"


def _finalize(state: SellerCopilotState, canonical: Dict, issues: List[ValidationIssue], passed: bool) -> None:
    state["canonical_listing"] = canonical
    state["validation_passed"] = passed
    state["validation_result"] = ValidationResult(passed=passed, issues=issues)
    state["checkpoint"] = "B_complete" if passed else "B_validation_failed"


# PR4-cleanup REMOVED:
#   - validation_node (alias) → use validation_rules_node
# alias 다시 추가 금지 (architecture.md "노드 이름 일관성 원칙" 참조).
