"""
Agent 3 — 판매글 생성

분류 (Target Architecture, 4+2+5):
  copywriting_node  → Single Tool Node (with deterministic fallback chain)

  PR2에서 ReAct 패턴 제거. critic이 repair_action·rewrite_plan을 결정해
  보내주면 copywriting은 그걸 실행만 한다 (selection 없음).

  분기는 단일 if문:
    - state.rewrite_plan.target ∈ {"title", "description", "full"} → 부분/전체 재작성
    - state.rewrite_plan 없음 (신규 세션 또는 critic이 rewrite 안 보냄) → 신규 generate

  fallback 체인 (단일 호출 실패 시 결정론):
    1. LLM (ListingService) — 신규 generate 또는 rewrite
    2. _apply_rewrite_instruction_rule_based — rewrite 지시가 있는데 LLM 다 실패
    3. _build_template_listing — 최후의 결정론적 템플릿

  refinement_node는 PR2에서 validation_agent.py에 흡수 후 삭제됨.
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

import logging

from app.graph.seller_copilot_state import CanonicalListing, SellerCopilotState
from app.graph.nodes.helpers import (
    _log,
    _record_error,
    _record_node_timing,
    _run_async,
    _safe_int,
    _start_timer,
)


# ── 메인 노드 ─────────────────────────────────────────────────────


def copywriting_node(state: SellerCopilotState) -> SellerCopilotState:
    """단일 툴 노드. critic이 정해준 rewrite_plan을 실행하거나 신규 generate."""
    _timer = _start_timer()
    _log(state, "agent3:copywriting:start")

    product = state.get("confirmed_product")
    if not product:
        _record_error(state, "copywriting_node", "confirmed_product missing")
        state["status"] = "failed"
        return state

    market_context = state.get("market_context") or {}
    strategy = state.get("strategy") or {}
    image_paths = state.get("image_paths") or []

    # critic이 정해준 rewrite_plan 우선 — 없으면 legacy rewrite_instruction fallback
    rewrite_plan = state.get("rewrite_plan") or {}
    rewrite_instruction = rewrite_plan.get("instruction") or state.get("rewrite_instruction")
    rewrite_target = rewrite_plan.get("target")  # "title" | "description" | "full" | None

    is_rewrite = bool(rewrite_instruction)
    _log(
        state,
        f"agent3:mode={'rewrite' if is_rewrite else 'generate'} "
        f"target={rewrite_target or 'n/a'} has_instruction={bool(rewrite_instruction)}",
    )

    new_listing = _call_listing_service(
        state, product, market_context, strategy, image_paths,
        rewrite_instruction, rewrite_target,
    )

    state["canonical_listing"] = _resolve_final_listing(
        new_listing, state, product, strategy, market_context, image_paths, rewrite_instruction,
    )

    # rewrite 실행 후 정리 — 같은 지시가 다음 사이클에 재실행되지 않게
    if is_rewrite:
        state["rewrite_instruction"] = None
        state["rewrite_plan"] = {}

    state["checkpoint"] = "B_draft_complete"
    state["status"] = "draft_generated"
    _record_node_timing(state, "copywriting", _timer)
    return state


# ── 정책: 최종 listing 결정 ──────────────────────────────────────


def _resolve_final_listing(
    new_listing: Optional[Dict],
    state: SellerCopilotState,
    product: Dict,
    strategy: Dict,
    market_context: Dict,
    image_paths: List[str],
    rewrite_instruction: Optional[str],
) -> Dict:
    """최종 canonical_listing을 결정하는 정책 함수.

    정책 매트릭스:
    ┌───────────────────────┬────────────────────────┬─────────────────────────────┐
    │ 조건                   │ 결과                    │ 근거                         │
    ├───────────────────────┼────────────────────────┼─────────────────────────────┤
    │ new_listing 있음       │ normalize 후 사용       │ LLM/fallback 성공            │
    │ rewrite + 기존 있음    │ 기존 유지 + 지시 반영   │ template 신규 생성 금지       │
    │ 기존 listing 없음      │ template 신규 생성      │ 최초 생성만 허용              │
    │ 기존 listing 있음      │ 기존 유지               │ 변경 없음                    │
    └───────────────────────┴────────────────────────┴─────────────────────────────┘
    """
    existing = state.get("canonical_listing")

    if new_listing:
        _log(state, "agent3:policy:new_listing_accepted")
        return _normalize_listing(new_listing, product, strategy, image_paths)

    if rewrite_instruction and existing:
        _log(state, "agent3:policy:rewrite_all_failed → preserving existing + instruction")
        patched = dict(existing)
        patched["description"] = f"{patched.get('description', '')}\n\n[판매자 수정 요청] {rewrite_instruction}".strip()
        return patched

    if not existing:
        _log(state, "agent3:policy:no_listing → template")
        return _build_template_listing(product, strategy, market_context, state)

    _log(state, "agent3:policy:existing_listing_preserved")
    return existing


# ── 단일 LLM 호출 (Single Tool) + 결정론적 fallback 체인 ─────────


def _call_listing_service(
    state: SellerCopilotState,
    product: Dict,
    market_context: Dict,
    strategy: Dict,
    image_paths: List[str],
    rewrite_instruction: Optional[str],
    rewrite_target: Optional[str],
) -> Optional[Dict]:
    """ListingService 단일 호출 (LLM 1회). 실패 시 결정론적 fallback 체인.

    fallback 단계:
      (1) LLM (ListingService.rewrite_listing 또는 build_canonical_listing)
      (2) rewrite 지시가 있으면 _apply_rewrite_instruction_rule_based
      (3) _build_template_listing (최후)
    """
    existing = state.get("canonical_listing")

    # ── (1) LLM 호출 ─────────────────────────────────────────────
    try:
        from app.services.listing_service import ListingService
        svc = ListingService()

        if rewrite_instruction and existing:
            # rewrite_target에 따라 instruction에 컨텍스트 보강
            target_hint = _build_target_hint(rewrite_target)
            full_instruction = f"{target_hint} {rewrite_instruction}".strip() if target_hint else rewrite_instruction

            listing = _run_async(lambda: svc.rewrite_listing(
                canonical_listing=existing,
                rewrite_instruction=full_instruction,
                confirmed_product=product,
                market_context=market_context,
                strategy=strategy,
            ))
            _log(state, f"agent3:llm:rewrite:success target={rewrite_target or 'full'}")
            return listing

        listing = _run_async(lambda: svc.build_canonical_listing(
            confirmed_product=product,
            market_context=market_context,
            strategy=strategy,
            image_paths=image_paths,
        ))
        _log(state, "agent3:llm:generate:success")
        return listing

    except Exception as e:
        logging.getLogger(__name__).error("agent3 LLM call failed", exc_info=True)
        _record_error(state, "copywriting_node", f"llm failed: {e}")
        _log(state, f"agent3:llm:failed error={e} → rule-based / template fallback")

    # ── (2) rule-based rewrite ──────────────────────────────────
    if rewrite_instruction and existing:
        _log(state, f"agent3:fallback:rule_based_rewrite instruction={rewrite_instruction[:50]}")
        return _apply_rewrite_instruction_rule_based(existing, rewrite_instruction, product, strategy)

    if rewrite_instruction and not existing:
        _log(state, f"agent3:warning:rewrite_instruction_lost instruction={rewrite_instruction[:50]}")

    # ── (3) template ────────────────────────────────────────────
    return _build_template_listing(product, strategy, market_context, state)


def _build_target_hint(target: Optional[str]) -> str:
    """rewrite_plan.target에 따라 LLM 지시 앞에 붙일 컨텍스트."""
    if target == "title":
        return "[제목만 재작성]"
    if target == "description":
        return "[설명만 재작성]"
    if target == "full":
        return "[전체 재작성]"
    return ""


# ── 규칙 기반 재작성 (LLM 완전 실패 시 최후 수단) ─────────────────


def _apply_rewrite_instruction_rule_based(
    existing: Dict, instruction: str, product: Dict, strategy: Dict,
) -> Dict:
    """LLM/서비스 모두 실패 시 rewrite_instruction을 규칙 기반으로 기존 listing에 반영.

    가격 변경 지시 → 가격 필드 직접 수정
    설명 추가/수정 지시 → description에 append
    그 외 → description 끝에 지시 내용 반영
    """
    patched = dict(existing)
    lower = instruction.lower()

    price_match = re.search(r'(\d[\d,]*)\s*원', instruction)
    if price_match and any(kw in lower for kw in ("가격", "원으로", "인하", "인상", "할인")):
        new_price = int(price_match.group(1).replace(",", ""))
        if new_price > 0:
            patched["price"] = new_price

    desc = patched.get("description") or ""
    patched["description"] = f"{desc}\n\n[판매자 수정] {instruction}".strip()

    patched.setdefault("title", f"{product.get('model', '상품')} 판매합니다")
    patched.setdefault("price", _safe_int(strategy.get("recommended_price"), 0))
    patched.setdefault("tags", [product.get("model", "상품")])
    patched.setdefault("images", [])
    patched.setdefault("product", product)
    patched.setdefault("strategy", strategy.get("goal", "fast_sell"))

    return patched


# ── 정규화 ────────────────────────────────────────────────────────


def _normalize_listing(
    listing: Dict, product: Dict, strategy: Dict, image_paths: list,
) -> Dict:
    """LLM 결과를 CanonicalListingSchema 계약에 맞게 정규화."""
    try:
        from app.domain.schemas import CanonicalListingSchema
        if listing.get("title"):
            schema = CanonicalListingSchema(
                title=listing.get("title", ""),
                description=listing.get("description", ""),
                price=listing.get("price") or strategy.get("recommended_price", 0),
                tags=listing.get("tags") or [],
                images=listing.get("images") or image_paths,
                strategy=listing.get("strategy") or strategy.get("goal", "fast_sell"),
                product=listing.get("product") or product,
            )
            return schema.model_dump()
    except (ValueError, TypeError, KeyError):
        pass
    listing.setdefault("title", f"{product.get('model', '상품')} 판매합니다")
    listing.setdefault("description", "AI가 생성한 판매글 초안")
    listing.setdefault("price", _safe_int(strategy.get("recommended_price"), 0))
    listing.setdefault("tags", [product.get("model", "상품")])
    listing.setdefault("images", image_paths)
    listing.setdefault("product", product)
    listing.setdefault("strategy", strategy.get("goal", "fast_sell"))
    return listing


# ── 템플릿 ─────────────────────────────────────────────────────────


def _build_template_listing(
    product: Dict, strategy: Dict, market_context: Dict, state: SellerCopilotState
) -> Dict:
    brand = product.get("brand") or ""
    model = product.get("model") or "상품"
    price = _safe_int(strategy.get("recommended_price"), 0)
    brand_prefix = f"{brand} " if brand and brand.lower() != "unknown" else ""

    return CanonicalListing(
        title=f"{brand_prefix}{model} 판매합니다".strip(),
        description=(
            f"{brand_prefix}{model} 판매합니다.\n"
            f"상태는 사진 참고 부탁드립니다.\n"
            f"문의 환영합니다."
        ),
        tags=[t for t in [model, brand, product.get("category")] if t and t.lower() != "unknown"][:5],
        price=price,
        images=state.get("image_paths") or [],
        strategy=strategy.get("goal", "fast_sell"),
        product=product,
    )


# refinement_node는 PR2에서 validation_agent.py로 흡수 후 삭제됨.
# 호환을 위해 import 시점에 ImportError가 나지 않도록 alias만 남겨두고,
# 호출되면 단순히 state를 그대로 반환 (validation_node가 이미 보강함).
def refinement_node(state: SellerCopilotState) -> SellerCopilotState:
    """Deprecated: validation_node가 흡수. 호출되면 no-op."""
    _log(state, "agent3:refinement:deprecated_noop (validation_node가 보강 처리)")
    return state
