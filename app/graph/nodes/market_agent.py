"""
Agent 2 — 시세·가격 (Tool Agent + Deterministic)

분류 (Target Architecture, 4+2+5):
  market_intelligence_node  → Tool Agent (ReAct)
                              lc_market_crawl_tool + lc_rag_price_tool 자율 선택.
                              PR3에서 state.market_depth 정책 반영
                              ("crawl_only"이면 RAG tool bind 제외).
  pricing_strategy_node     → Deterministic Node (PR1 알리아스: pricing_rule_node)
                              goal_strategy 모듈 기반 규칙 산정. LLM 호출 없음.
"""
from __future__ import annotations

import logging

from app.graph.seller_copilot_state import MarketContext, PricingStrategy, SellerCopilotState
from app.graph.nodes.helpers import (
    _build_react_llm,
    _extract_market_context,
    _log,
    _record_error,
    _record_tool_call,
    _run_async,
    _safe_int,
)


def market_intelligence_node(state: SellerCopilotState) -> SellerCopilotState:
    _log(state, "agent2:market_intelligence:start")

    product = state.get("confirmed_product")
    if not product:
        _record_error(state, "market_intelligence_node", "confirmed_product missing")
        state["status"] = "failed"
        return state

    # 이미 주입된 market_context가 있으면 스킵 (테스트/API 주입 경로)
    existing_ctx = state.get("market_context") or {}
    if existing_ctx and _safe_int(existing_ctx.get("sample_count"), 0) > 0:
        _log(state, "agent2:market_intelligence:using_precomputed_context")
        state["checkpoint"] = "B_market_complete"
        return state

    # ── ReAct 에이전트: LLM이 툴을 자율 선택 ────────────────────
    from app.tools.agentic_tools import lc_market_crawl_tool, lc_rag_price_tool

    brand = product.get("brand", "")
    model = product.get("model", "")
    category = product.get("category", "")

    system_prompt = """당신은 중고거래 시세 분석 전문가입니다.
주어진 상품의 현재 시세를 조사하고 가격 전략 수립에 필요한 정보를 수집합니다.

반드시 따라야 할 규칙:
1. lc_market_crawl_tool을 먼저 호출해 현재 매물 시세를 수집한다.
2. 결과의 sample_count가 3 미만이면 lc_rag_price_tool을 추가로 호출해 보완한다.
3. 모든 수집이 끝나면 최종 JSON을 반환한다.

최종 응답 형식 (JSON만, 설명 없이):
{"median_price": 숫자, "price_band": [최저, 최고], "sample_count": 숫자, "crawler_sources": ["플랫폼명"]}"""

    user_prompt = f"""상품 정보:
- 브랜드: {brand}
- 모델: {model}
- 카테고리: {category}

위 상품의 중고 시세를 조사하고 최종 JSON을 반환하라."""

    market_context_result = None

    try:
        from langchain_core.messages import HumanMessage

        llm = _build_react_llm()
        if llm is None:
            raise ValueError("LLM 초기화 실패 — API 키 확인 필요")

        from langchain.agents import create_agent
        agent = create_agent(
            llm,
            [lc_market_crawl_tool, lc_rag_price_tool],
            system_prompt=system_prompt,
        )

        _log(state, "agent2:react_agent:invoking LLM with tools=[market_crawl, rag_price]")
        msgs = [HumanMessage(content=user_prompt)]
        result = _run_async(lambda: agent.ainvoke({"messages": msgs}))

        for msg in result.get("messages", []):
            if hasattr(msg, "tool_calls") and msg.tool_calls:
                for tc in msg.tool_calls:
                    _log(state, f"agent2:llm_selected_tool:{tc.get('name', tc.get('type', '?'))}")
                    _record_tool_call(state, {
                        "tool_name": tc.get("name", ""),
                        "input": tc.get("args", {}),
                        "output": None,
                        "success": True,
                    })

        final_content = result["messages"][-1].content
        _log(state, f"agent2:react_agent:final_response={final_content[:100]}")
        market_context_result = _extract_market_context(final_content)

    except Exception as e:
        logging.getLogger(__name__).error("agent2 ReAct agent failed", exc_info=True)
        _record_error(state, "market_intelligence_node", f"react_agent failed: {e}")
        _log(state, f"agent2:react_agent:failed error={e} → fallback to direct tool call")

        # Fallback: 직접 툴 호출
        from app.tools.agentic_tools import market_crawl_tool, rag_price_tool
        crawl_result = _run_async(lambda: market_crawl_tool(product))
        _record_tool_call(state, crawl_result)
        crawl_output = crawl_result.get("output") or {}
        sample_count = _safe_int(crawl_output.get("sample_count"), 0)

        if sample_count < 3:
            _log(state, f"agent2:fallback:sample_count={sample_count}<3 → rag_price_tool")
            rag_result = _run_async(lambda: rag_price_tool(product))
            _record_tool_call(state, rag_result)

        market_context_result = {
            "median_price": crawl_output.get("median_price"),
            "price_band": crawl_output.get("price_band") or [],
            "sample_count": sample_count,
            "crawler_sources": crawl_output.get("crawler_sources") or [],
            "reference_listings": crawl_output.get("raw_listings") or [],
        }

    state["market_context"] = MarketContext(
        price_band=market_context_result.get("price_band") or [],
        median_price=market_context_result.get("median_price"),
        sample_count=_safe_int(market_context_result.get("sample_count"), 0),
        crawler_sources=market_context_result.get("crawler_sources") or [],
        reference_listings=market_context_result.get("reference_listings") or [],
    )
    state["checkpoint"] = "B_market_complete"
    state["status"] = "market_analyzing"
    _log(state, f"agent2:market_intelligence:done sample_count={market_context_result.get('sample_count')}")
    return state


def pricing_strategy_node(state: SellerCopilotState) -> SellerCopilotState:
    _log(state, "agent2:pricing_strategy:start")

    from app.domain.goal_strategy import get_negotiation_policy, get_pricing_multiplier

    market_context = state.get("market_context") or {}
    median_price = _safe_int(market_context.get("median_price"), 0)
    sample_count = _safe_int(market_context.get("sample_count"), 0)
    goal = state.get("mission_goal", "balanced")

    multiplier = get_pricing_multiplier(goal, sample_count)
    if median_price > 0:
        recommended_price = int(round(median_price * multiplier, -3))
        _log(state, f"agent2:pricing:goal={goal} multiplier={multiplier} price={recommended_price}")
    else:
        recommended_price = 0
        _log(state, f"agent2:pricing:no_market_data goal={goal} price=0")

    state["strategy"] = PricingStrategy(
        goal=goal,
        recommended_price=recommended_price,
        negotiation_policy=get_negotiation_policy(goal),
    )
    state["checkpoint"] = "B_strategy_complete"
    return state


# ── PR1 알리아스 (Target Architecture: 4+2+5 재분류) ──────────────────
# 동작 변화 0. PR2/3에서 신 이름이 routing.py·graph builder에서 사용되기 시작.
pricing_rule_node = pricing_strategy_node
