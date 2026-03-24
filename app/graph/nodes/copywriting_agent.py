"""
Agent 3 — 판매글 생성 에이전트 (ReAct)

노드:
  copywriting_node   — lc_generate_listing_tool / lc_rewrite_listing_tool 자율 선택
  refinement_node    — validation 실패 시 자동 보완 (Agent 4 루프)

내부 함수 분리:
  _run_copywriting_agent()    — ReAct 에이전트 실행
  _extract_listing_payload()  — 에이전트 결과에서 listing dict 추출
  _normalize_listing()        — 추출 결과를 CanonicalListingSchema 계약에 맞게 정규화
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from app.graph.seller_copilot_state import CanonicalListing, SellerCopilotState
from app.graph.nodes.helpers import (
    _build_react_llm,
    _log,
    _record_error,
    _record_tool_call,
    _run_async,
    _safe_int,
)


# ── 메인 노드 ─────────────────────────────────────────────────────


def copywriting_node(state: SellerCopilotState) -> SellerCopilotState:
    _log(state, "agent3:copywriting:start")

    product = state.get("confirmed_product")
    if not product:
        _record_error(state, "copywriting_node", "confirmed_product missing")
        state["status"] = "failed"
        return state

    market_context = state.get("market_context") or {}
    strategy = state.get("strategy") or {}
    rewrite_instruction = state.get("rewrite_instruction")
    image_paths = state.get("image_paths") or []

    new_listing = _run_copywriting_agent(state, product, market_context, strategy, image_paths, rewrite_instruction)

    if new_listing:
        new_listing = _normalize_listing(new_listing, product, strategy, image_paths)
        state["canonical_listing"] = new_listing
        state["rewrite_instruction"] = None
    elif not state.get("canonical_listing"):
        state["canonical_listing"] = _build_template_listing(product, strategy, market_context, state)

    state["checkpoint"] = "B_draft_complete"
    state["status"] = "draft_generated"
    return state


# ── 에이전트 실행 ─────────────────────────────────────────────────


def _run_copywriting_agent(
    state: SellerCopilotState,
    product: Dict,
    market_context: Dict,
    strategy: Dict,
    image_paths: List[str],
    rewrite_instruction: Optional[str],
) -> Optional[Dict]:
    """ReAct 에이전트를 실행하고 listing dict를 반환한다. 실패 시 fallback 체인."""
    from app.tools.agentic_tools import lc_generate_listing_tool, lc_rewrite_listing_tool

    system_prompt, user_prompt = _build_prompts(state, product, market_context, strategy, image_paths, rewrite_instruction)

    try:
        from langchain_core.messages import HumanMessage

        llm = _build_react_llm()
        if llm is None:
            raise ValueError("LLM 초기화 실패 — API 키 확인 필요")

        from langchain.agents import create_agent
        agent = create_agent(
            llm,
            [lc_generate_listing_tool, lc_rewrite_listing_tool],
            system_prompt=system_prompt,
        )

        _log(state, "agent3:react_agent:invoking LLM with tools=[generate_listing, rewrite_listing]")
        msgs = [HumanMessage(content=user_prompt)]
        result = _run_async(lambda: agent.ainvoke({"messages": msgs}))

        # tool call 기록
        for msg in result.get("messages", []):
            if hasattr(msg, "tool_calls") and msg.tool_calls:
                for tc in msg.tool_calls:
                    _log(state, f"agent3:llm_selected_tool:{tc.get('name', '?')}")
                    _record_tool_call(state, {
                        "tool_name": tc.get("name", ""),
                        "input": tc.get("args", {}),
                        "output": None,
                        "success": True,
                    })

        return _extract_listing_payload(result, state)

    except Exception as e:
        _record_error(state, "copywriting_node", f"react_agent failed: {e}")
        _log(state, f"agent3:react_agent:failed error={e} → fallback to direct service call")
        return _fallback_generate(state, product, market_context, strategy, image_paths)


def _fallback_generate(
    state: SellerCopilotState,
    product: Dict,
    market_context: Dict,
    strategy: Dict,
    image_paths: List[str],
) -> Optional[Dict]:
    """ReAct 실패 시 ListingService 직접 호출 → 그것도 실패 시 template."""
    try:
        from app.services.listing_service import ListingService
        svc = ListingService()
        listing = _run_async(lambda: svc.build_canonical_listing(
            confirmed_product=product,
            market_context=market_context,
            strategy=strategy,
            image_paths=image_paths,
        ))
        _log(state, "agent3:fallback:direct_service_call:success")
        return listing
    except Exception as e2:
        _record_error(state, "copywriting_node", f"fallback failed: {e2}")
        _log(state, f"agent3:fallback:failed error={e2} → template")
        return _build_template_listing(product, strategy, market_context, state)


# ── 프롬프트 빌드 ────────────────────────────────────────────────


def _build_prompts(
    state: SellerCopilotState,
    product: Dict,
    market_context: Dict,
    strategy: Dict,
    image_paths: List[str],
    rewrite_instruction: Optional[str],
) -> tuple[str, str]:
    """시스템 프롬프트와 유저 프롬프트를 빌드한다."""
    existing_listing = state.get("canonical_listing")

    existing_summary = ""
    if existing_listing:
        existing_summary = (
            f"\n현재 판매글:\n"
            f"- 제목: {existing_listing.get('title', '')}\n"
            f"- 설명: {(existing_listing.get('description') or '')[:120]}...\n"
            f"- 가격: {existing_listing.get('price', 0)}원"
        )

    if rewrite_instruction:
        task_directive = (
            f"\n[작업] 사용자 수정 요청: \"{rewrite_instruction}\"\n"
            f"→ lc_rewrite_listing_tool을 호출해 기존 판매글을 수정하라."
        )
    else:
        task_directive = (
            "\n[작업] 수정 요청 없음 — 신규 판매글 생성.\n"
            "→ lc_generate_listing_tool을 호출해 새 판매글을 생성하라."
        )

    prior_tool_calls = "\n".join([
        f"- {tc.get('tool_name')}: {str(tc.get('input', {}))[:60]}"
        for tc in (state.get("tool_calls") or [])[-3:]
    ])

    system_prompt = (
        "당신은 중고거래 카피라이팅 전문 에이전트입니다.\n"
        "주어진 상품 정보와 시장 데이터를 활용해 매력적인 판매글을 작성합니다.\n\n"
        "규칙:\n"
        "1. rewrite_instruction이 있으면 반드시 lc_rewrite_listing_tool을 호출한다.\n"
        "2. rewrite_instruction이 없으면 반드시 lc_generate_listing_tool을 호출한다.\n"
        "3. 툴 호출 결과(JSON)를 그대로 최종 응답으로 출력한다."
    )

    selected_platforms = state.get("selected_platforms") or ["bunjang", "joongna"]
    user_prompt = (
        f"상품 정보:\n"
        f"- 브랜드: {product.get('brand', '')}\n"
        f"- 모델: {product.get('model', '')}\n"
        f"- 카테고리: {product.get('category', '')}\n"
        f"- 추천 가격: {_safe_int(strategy.get('recommended_price'), 0)}원\n"
        f"- 이미지 경로: {json.dumps(image_paths, ensure_ascii=False)}\n"
        f"- 플랫폼: {json.dumps(selected_platforms, ensure_ascii=False)}\n"
        f"{existing_summary}"
        f"{task_directive}\n"
        + (f"\n이전 툴 호출 기록:\n{prior_tool_calls}" if prior_tool_calls else "")
    )

    return system_prompt, user_prompt


# ── 결과 추출 ─────────────────────────────────────────────────────


def _extract_listing_payload(result: Dict, state: SellerCopilotState) -> Optional[Dict]:
    """에이전트 결과 messages에서 listing dict를 추출한다."""
    for msg in reversed(result.get("messages", [])):
        content = getattr(msg, "content", "") or ""
        if not content:
            continue
        try:
            parsed = json.loads(content) if isinstance(content, str) else content
            if isinstance(parsed, dict) and "title" in parsed:
                _log(state, f"agent3:react_agent:listing_extracted title={parsed.get('title', '')[:40]}")
                return parsed
        except Exception:
            pass

    # regex fallback
    final_content = str(result.get("messages", [{}])[-1].content or "") if result.get("messages") else ""
    _log(state, f"agent3:react_agent:final_response={final_content[:100]}")
    m = re.search(r'\{[^{}]*"title"[^{}]*\}', final_content, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            pass

    return None


# ── 정규화 ────────────────────────────────────────────────────────


def _normalize_listing(
    listing: Dict, product: Dict, strategy: Dict, image_paths: list,
) -> Dict:
    """ReAct/LLM 결과를 CanonicalListingSchema 계약에 맞게 정규화."""
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
    except Exception:
        pass
    # fallback: 최소 필수 키 보장
    listing.setdefault("title", f"{product.get('model', '상품')} 판매합니다")
    listing.setdefault("description", "AI가 생성한 판매글 초안")
    listing.setdefault("price", _safe_int(strategy.get("recommended_price"), 0))
    listing.setdefault("tags", [product.get("model", "상품")])
    listing.setdefault("images", image_paths)
    listing.setdefault("product", product)
    listing.setdefault("strategy", strategy.get("goal", "fast_sell"))
    return listing


# ── 템플릿 / refinement ──────────────────────────────────────────


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


def refinement_node(state: SellerCopilotState) -> SellerCopilotState:
    """validation 실패 시 에이전트 4가 자동으로 listing을 수정"""
    _log(state, "agent4:refinement:start")

    canonical = dict(state.get("canonical_listing") or {})
    market_context = state.get("market_context") or {}
    strategy = state.get("strategy") or {}

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

    state["canonical_listing"] = canonical
    _log(state, "agent4:refinement:done")
    return state
