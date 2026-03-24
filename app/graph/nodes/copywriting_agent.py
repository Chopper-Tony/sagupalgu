"""
Agent 3 — 판매글 생성 에이전트 (ReAct)

노드:
  copywriting_node   — lc_generate_listing_tool / lc_rewrite_listing_tool 자율 선택
  refinement_node    — validation 실패 시 자동 보완 (Agent 4 루프)
"""
from __future__ import annotations

import json
from typing import Any, Dict

from app.graph.seller_copilot_state import CanonicalListing, SellerCopilotState
from app.graph.nodes.helpers import (
    _build_react_llm,
    _log,
    _record_error,
    _record_tool_call,
    _run_async,
    _safe_int,
)


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
    existing_listing = state.get("canonical_listing")

    from app.tools.listing_tools import lc_generate_listing_tool, lc_rewrite_listing_tool
    from langchain_core.messages import HumanMessage

    brand = product.get("brand", "")
    model = product.get("model", "")
    category = product.get("category", "")
    recommended_price = _safe_int(strategy.get("recommended_price"), 0)
    image_paths = state.get("image_paths") or []
    selected_platforms = state.get("selected_platforms") or ["bunjang", "joongna"]

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

    user_prompt = (
        f"상품 정보:\n"
        f"- 브랜드: {brand}\n"
        f"- 모델: {model}\n"
        f"- 카테고리: {category}\n"
        f"- 추천 가격: {recommended_price}원\n"
        f"- 이미지 경로: {json.dumps(image_paths, ensure_ascii=False)}\n"
        f"- 플랫폼: {json.dumps(selected_platforms, ensure_ascii=False)}\n"
        f"{existing_summary}"
        f"{task_directive}\n"
        + (f"\n이전 툴 호출 기록:\n{prior_tool_calls}" if prior_tool_calls else "")
    )

    new_listing = None

    try:
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

        for msg in reversed(result.get("messages", [])):
            content = getattr(msg, "content", "") or ""
            if not content:
                continue
            try:
                parsed = json.loads(content) if isinstance(content, str) else content
                if isinstance(parsed, dict) and "title" in parsed:
                    new_listing = parsed
                    _log(state, f"agent3:react_agent:listing_extracted title={parsed.get('title', '')[:40]}")
                    break
            except Exception:
                pass

        if not new_listing:
            import re
            final_content = str(result["messages"][-1].content or "")
            _log(state, f"agent3:react_agent:final_response={final_content[:100]}")
            m = re.search(r'\{[^{}]*"title"[^{}]*\}', final_content, re.DOTALL)
            if m:
                try:
                    new_listing = json.loads(m.group(0))
                except Exception:
                    pass

    except Exception as e:
        _record_error(state, "copywriting_node", f"react_agent failed: {e}")
        _log(state, f"agent3:react_agent:failed error={e} → fallback to direct service call")

        try:
            from app.services.listing_service import ListingService
            svc = ListingService()
            new_listing = _run_async(lambda: svc.build_canonical_listing(
                confirmed_product=product,
                market_context=market_context,
                strategy=strategy,
                image_paths=image_paths,
            ))
            _log(state, "agent3:fallback:direct_service_call:success")
        except Exception as e2:
            _record_error(state, "copywriting_node", f"fallback failed: {e2}")
            _log(state, f"agent3:fallback:failed error={e2} → template")
            new_listing = _build_template_listing(product, strategy, market_context, state)

    if new_listing:
        if not new_listing.get("images"):
            new_listing["images"] = image_paths
        if "product" not in new_listing:
            new_listing["product"] = product
        if "strategy" not in new_listing:
            new_listing["strategy"] = strategy.get("goal", "fast_sell")
        state["canonical_listing"] = new_listing
        state["rewrite_instruction"] = None
    elif not state.get("canonical_listing"):
        state["canonical_listing"] = _build_template_listing(product, strategy, market_context, state)

    state["checkpoint"] = "B_draft_complete"
    state["status"] = "draft_generated"
    return state


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
