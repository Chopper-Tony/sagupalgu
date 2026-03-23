"""
LangGraph 노드 구현 — 진짜 에이전틱 버전.

각 노드(에이전트)는:
1. state를 읽고 상황을 판단
2. 필요한 도구를 자율적으로 선택·호출
3. 결과를 state에 반영
4. 다음 노드에서 라우팅 판단에 쓸 신호를 state에 명확히 기록
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from app.graph.seller_copilot_state import (
    CanonicalListing,
    ConfirmedProduct,
    MarketContext,
    PricingStrategy,
    SellerCopilotState,
    ValidationIssue,
    ValidationResult,
)


# ── 헬퍼 ──────────────────────────────────────────────────────────

def _log(state: SellerCopilotState, msg: str) -> None:
    logs = state.get("debug_logs") or []
    logs.append(f"[{datetime.now(timezone.utc).isoformat()}] {msg}")
    state["debug_logs"] = logs


def _record_tool_call(state: SellerCopilotState, call: Dict[str, Any]) -> None:
    calls = state.get("tool_calls") or []
    calls.append(call)
    state["tool_calls"] = calls


def _record_error(state: SellerCopilotState, source: str, error: str) -> None:
    history = state.get("error_history") or []
    history.append({
        "source": source,
        "error": error,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    state["error_history"] = history
    state["last_error"] = error


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _run_async(coro):
    """동기 컨텍스트에서 async 도구 실행"""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, coro)
                return future.result()
        return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


def _build_react_llm():
    """ReAct 에이전트용 LLM 초기화 (bind_tools 지원 모델)"""
    from app.core.config import settings
    try:
        if settings.gemini_api_key:
            from langchain_google_genai import ChatGoogleGenerativeAI
            return ChatGoogleGenerativeAI(
                model=settings.gemini_listing_model,
                google_api_key=settings.gemini_api_key,
                temperature=0.0,
            )
    except Exception:
        pass
    try:
        if settings.openai_api_key:
            from langchain_openai import ChatOpenAI
            return ChatOpenAI(
                model=settings.openai_listing_model,
                api_key=settings.openai_api_key,
                temperature=0.0,
            )
    except Exception:
        pass
    return None


def _extract_market_context(text: str) -> dict:
    """LLM 최종 응답에서 market_context JSON 파싱"""
    import json, re
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text).strip()
        text = re.sub(r"```$", "", text).strip()
    try:
        data = json.loads(text)
        return {
            "median_price": data.get("median_price"),
            "price_band": data.get("price_band") or [],
            "sample_count": int(data.get("sample_count") or 0),
            "crawler_sources": data.get("crawler_sources") or [],
        }
    except Exception:
        m = re.search(r"\{.*?\}", text, re.DOTALL)
        if m:
            try:
                data = json.loads(m.group(0))
                return {
                    "median_price": data.get("median_price"),
                    "price_band": data.get("price_band") or [],
                    "sample_count": int(data.get("sample_count") or 0),
                    "crawler_sources": data.get("crawler_sources") or [],
                }
            except Exception:
                pass
    return {"median_price": None, "price_band": [], "sample_count": 0, "crawler_sources": []}


# ══════════════════════════════════════════════════════════════════
# 에이전트 1: 상품 식별 에이전트
# 판단: user_product_input이 있으면 바로 확정
#       없으면 product_candidates confidence 체크
#       confidence < 0.6 이면 사용자 입력 요청
# ══════════════════════════════════════════════════════════════════

def product_identity_node(state: SellerCopilotState) -> SellerCopilotState:
    _log(state, "agent1:product_identity:start")

    user_input = state.get("user_product_input") or {}
    candidates = state.get("product_candidates") or []

    # 경로 A: 사용자가 직접 입력한 경우 → 도구 불필요, 바로 확정
    if user_input and user_input.get("model"):
        confirmed = ConfirmedProduct(
            brand=user_input.get("brand", ""),
            model=user_input.get("model", ""),
            category=user_input.get("category", ""),
            confidence=1.0,
            source="user_input",
            storage=user_input.get("storage", ""),
        )
        state["confirmed_product"] = confirmed
        state["needs_user_input"] = False
        state["clarification_prompt"] = None
        state["checkpoint"] = "A_complete"
        state["status"] = "product_confirmed"
        _log(state, "agent1:product_identity:user_input_confirmed")
        return state

    # 경로 B: Vision 결과(candidates)가 이미 있는 경우
    if candidates:
        best = candidates[0]
        confidence = float(best.get("confidence", 0.0) or 0.0)
        model = (best.get("model") or "").strip().lower()

        # 에이전트 판단: confidence 낮으면 사용자 입력 요청
        if confidence < 0.6 or model in {"unknown", ""}:
            state["needs_user_input"] = True
            state["clarification_prompt"] = (
                "사진만으로 모델명을 정확히 식별하지 못했습니다. "
                "모델명을 직접 입력해 주세요."
            )
            state["checkpoint"] = "A_needs_user_input"
            state["status"] = "awaiting_product_confirmation"
            _log(state, f"agent1:product_identity:low_confidence={confidence:.2f}")
            return state

        # confidence 충분 → 확정
        confirmed = ConfirmedProduct(
            brand=best.get("brand", ""),
            model=best.get("model", ""),
            category=best.get("category", ""),
            confidence=confidence,
            source=best.get("source", "vision"),
            storage=best.get("storage", ""),
        )
        state["confirmed_product"] = confirmed
        state["needs_user_input"] = False
        state["clarification_prompt"] = None
        state["checkpoint"] = "A_complete"
        state["status"] = "product_confirmed"
        _log(state, f"agent1:product_identity:vision_confirmed confidence={confidence:.2f}")
        return state

    # 경로 C: candidates도 없음 → 사용자 입력 요청
    state["needs_user_input"] = True
    state["clarification_prompt"] = (
        "상품 정보를 파악하지 못했습니다. "
        "모델명을 직접 입력해주시거나 사진을 다시 업로드해주세요."
    )
    state["checkpoint"] = "A_needs_user_input"
    state["status"] = "awaiting_product_confirmation"
    _log(state, "agent1:product_identity:no_candidates")
    return state


def clarification_node(state: SellerCopilotState) -> SellerCopilotState:
    """사용자 입력 대기 — 이 노드에서 graph는 END로 중단되고 사용자 응답을 기다린다"""
    _log(state, "agent1:clarification:waiting_for_user_input")
    state["checkpoint"] = "A_needs_user_input"
    state["status"] = "awaiting_product_confirmation"
    return state


# ══════════════════════════════════════════════════════════════════
# 에이전트 2: 시세·가격 전략 에이전트
# 판단: 먼저 market_crawl_tool 호출
#       sample_count < 3이면 rag_price_tool도 추가 호출 (보완)
#       두 결과를 합산해서 시장 맥락 구성
# ══════════════════════════════════════════════════════════════════

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
    from langchain_core.messages import HumanMessage

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
        llm = _build_react_llm()
        if llm is None:
            raise ValueError("LLM 초기화 실패 — API 키 확인 필요")

        from langgraph.prebuilt import create_react_agent
        agent = create_react_agent(
            llm,
            [lc_market_crawl_tool, lc_rag_price_tool],
            prompt=system_prompt,
        )

        _log(state, "agent2:react_agent:invoking LLM with tools=[market_crawl, rag_price]")
        result = _run_async(agent.ainvoke({
            "messages": [HumanMessage(content=user_prompt)]
        }))

        # tool_calls 기록 (LLM이 실제로 호출한 툴 추적)
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

        # 최종 메시지에서 market_context 파싱
        final_content = result["messages"][-1].content
        _log(state, f"agent2:react_agent:final_response={final_content[:100]}")
        market_context_result = _extract_market_context(final_content)

    except Exception as e:
        _record_error(state, "market_intelligence_node", f"react_agent failed: {e}")
        _log(state, f"agent2:react_agent:failed error={e} → fallback to direct tool call")

        # Fallback: 직접 툴 호출 (Python 로직)
        from app.tools.agentic_tools import market_crawl_tool, rag_price_tool
        crawl_result = _run_async(market_crawl_tool(product))
        _record_tool_call(state, crawl_result)
        crawl_output = crawl_result.get("output") or {}
        sample_count = _safe_int(crawl_output.get("sample_count"), 0)

        if sample_count < 3:
            _log(state, f"agent2:fallback:sample_count={sample_count}<3 → rag_price_tool")
            rag_result = _run_async(rag_price_tool(product))
            _record_tool_call(state, rag_result)

        market_context_result = {
            "median_price": crawl_output.get("median_price"),
            "price_band": crawl_output.get("price_band") or [],
            "sample_count": sample_count,
            "crawler_sources": crawl_output.get("crawler_sources") or [],
        }

    state["market_context"] = MarketContext(
        price_band=market_context_result.get("price_band") or [],
        median_price=market_context_result.get("median_price"),
        sample_count=_safe_int(market_context_result.get("sample_count"), 0),
        crawler_sources=market_context_result.get("crawler_sources") or [],
    )
    state["checkpoint"] = "B_market_complete"
    state["status"] = "market_analyzing"
    _log(state, f"agent2:market_intelligence:done sample_count={market_context_result.get('sample_count')}")
    return state


def pricing_strategy_node(state: SellerCopilotState) -> SellerCopilotState:
    _log(state, "agent2:pricing_strategy:start")

    market_context = state.get("market_context") or {}
    median_price = _safe_int(market_context.get("median_price"), 0)
    sample_count = _safe_int(market_context.get("sample_count"), 0)

    # 에이전트 판단: 표본이 충분한지에 따라 전략 다르게
    if median_price > 0 and sample_count >= 3:
        recommended_price = int(round(median_price * 0.97, -3))  # 시세의 97%, 천원 단위
        goal = "fast_sell"
        _log(state, f"agent2:pricing:data_based price={recommended_price}")
    elif median_price > 0:
        recommended_price = int(round(median_price * 0.95, -3))  # 표본 부족 → 더 보수적
        goal = "fast_sell"
        _log(state, f"agent2:pricing:low_sample fallback price={recommended_price}")
    else:
        recommended_price = 0
        goal = "fast_sell"
        _log(state, "agent2:pricing:no_market_data price=0")

    state["strategy"] = PricingStrategy(
        goal=goal,
        recommended_price=recommended_price,
        negotiation_policy="small negotiation allowed",
    )
    state["checkpoint"] = "B_strategy_complete"
    return state


# ══════════════════════════════════════════════════════════════════
# 에이전트 3: 판매글 생성 에이전트
# 판단: rewrite_instruction이 있으면 rewrite_listing_tool 호출
#       없으면 ListingService로 신규 생성
# ══════════════════════════════════════════════════════════════════

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

    from app.tools.agentic_tools import lc_generate_listing_tool, lc_rewrite_listing_tool
    from langchain_core.messages import HumanMessage
    import json

    brand = product.get("brand", "")
    model = product.get("model", "")
    category = product.get("category", "")
    recommended_price = _safe_int(strategy.get("recommended_price"), 0)
    image_paths = state.get("image_paths") or []
    selected_platforms = state.get("selected_platforms") or ["bunjang", "joongna"]

    # 기존 listing 요약 (재작성 시 LLM 컨텍스트로 제공)
    existing_summary = ""
    if existing_listing:
        existing_summary = (
            f"\n현재 판매글:\n"
            f"- 제목: {existing_listing.get('title', '')}\n"
            f"- 설명: {(existing_listing.get('description') or '')[:120]}...\n"
            f"- 가격: {existing_listing.get('price', 0)}원"
        )

    # LLM에게 상황을 명확히 알려 툴 선택 유도
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

    # 이전 툴 호출 기록 (카피라이팅 판단에 활용)
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

        from langgraph.prebuilt import create_react_agent
        agent = create_react_agent(
            llm,
            [lc_generate_listing_tool, lc_rewrite_listing_tool],
            prompt=system_prompt,
        )

        _log(state, "agent3:react_agent:invoking LLM with tools=[generate_listing, rewrite_listing]")
        result = _run_async(agent.ainvoke({
            "messages": [HumanMessage(content=user_prompt)]
        }))

        # LLM이 선택한 툴 기록
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

        # ToolMessage 결과에서 listing JSON 추출
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

        # ToolMessage에서 못 찾으면 최종 메시지에서 JSON 추출 시도
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

        # Fallback: ListingService 직접 호출
        try:
            from app.services.listing_service import ListingService
            svc = ListingService()
            new_listing = _run_async(svc.build_canonical_listing(
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
        # CanonicalListing 필수 필드 보정
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


# ══════════════════════════════════════════════════════════════════
# 에이전트 4: 검증·복구 에이전트
# 판단 1 (validation): listing 품질 검사 → 실패 시 refinement_node로 분기
# 판단 2 (recovery):   publish_results에 실패가 있으면
#                      diagnose → discord_alert → auto_recoverable이면 재시도 신호
# ══════════════════════════════════════════════════════════════════

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


def refinement_node(state: SellerCopilotState) -> SellerCopilotState:
    """validation 실패 시 에이전트 4가 자동으로 listing을 수정"""
    _log(state, "agent4:refinement:start")

    canonical = dict(state.get("canonical_listing") or {})
    market_context = state.get("market_context") or {}
    strategy = state.get("strategy") or {}

    # 설명이 너무 짧으면 자동 보완
    description = (canonical.get("description") or "").strip()
    if len(description) < 20:
        canonical["description"] = (
            description + "\n제품 상태는 실사진을 참고해 주세요. 빠른 거래 원합니다."
        ).strip()

    # 가격이 없으면 시세에서 자동 계산
    price = _safe_int(canonical.get("price"), 0)
    if price <= 0:
        median = _safe_int(market_context.get("median_price"), 0)
        recommended = _safe_int(strategy.get("recommended_price"), 0)
        canonical["price"] = recommended or (int(median * 0.97) if median > 0 else 0)

    state["canonical_listing"] = canonical
    _log(state, "agent4:refinement:done")
    return state


def recovery_node(state: SellerCopilotState) -> SellerCopilotState:
    """
    게시 실패 후 복구 에이전트.
    1. diagnose_publish_failure_tool — 원인 진단
    2. auto_patch_tool — 자동 패치 생성 (Agent 4의 핵심)
    3. discord_alert_tool — 알림 발송
    """
    _log(state, "agent4:recovery:start")

    from app.tools.agentic_tools import (
        diagnose_publish_failure_tool,
        auto_patch_tool,
        discord_alert_tool,
    )

    publish_results = state.get("publish_results") or {}
    canonical = state.get("canonical_listing") or {}
    diagnostics = []
    patches = []
    any_auto_recoverable = False

    for platform, result in publish_results.items():
        if result.get("success"):
            continue

        # ── 툴 1: 장애 진단 ──────────────────────────────────────
        _log(state, f"agent4:selecting_tool:diagnose_publish_failure platform={platform}")
        diag_call = diagnose_publish_failure_tool(
            platform=platform,
            error_code=result.get("error_code", "unknown"),
            error_message=result.get("error_message", ""),
        )
        _record_tool_call(state, diag_call)
        diag = diag_call.get("output") or {}
        diagnostics.append(diag)

        # ── 툴 2: 자동 패치 제안 (Agent 4 핵심 툴) ───────────────
        _log(state, f"agent4:selecting_tool:auto_patch_tool cause={diag.get('likely_cause')}")
        patch_call = _run_async(auto_patch_tool(
            platform=platform,
            likely_cause=diag.get("likely_cause", "unknown"),
            canonical_listing=canonical,
            session_id=state.get("session_id", "unknown"),
        ))
        _record_tool_call(state, patch_call)
        patch = patch_call.get("output") or {}
        patches.append(patch)

        if patch.get("auto_executable") or diag.get("auto_recoverable"):
            any_auto_recoverable = True

        # ── 툴 3: Discord 알림 ───────────────────────────────────
        _log(state, "agent4:selecting_tool:discord_alert_tool")
        alert_msg = (
            f"[{platform}] 게시 실패\n"
            f"원인: {diag.get('likely_cause')}\n"
            f"진단: {diag.get('patch_suggestion')}\n"
            f"자동패치: {patch.get('type')} | 실행가능: {patch.get('auto_executable')}"
        )
        alert_call = _run_async(discord_alert_tool(
            message=alert_msg,
            session_id=state.get("session_id", "unknown"),
            level="error",
        ))
        _record_tool_call(state, alert_call)

    state["publish_diagnostics"] = diagnostics
    state["patch_suggestions"] = patches
    state["should_retry_publish"] = any_auto_recoverable

    retry_count = _safe_int(state.get("publish_retry_count"), 0)
    if any_auto_recoverable and retry_count < 2:
        state["publish_retry_count"] = retry_count + 1
        state["checkpoint"] = "D_recovering"
        _log(state, f"agent4:recovery:auto_recoverable retry={retry_count+1}")
    else:
        state["checkpoint"] = "D_publish_failed"
        state["status"] = "publishing_failed"
        _log(state, "agent4:recovery:not_recoverable → publishing_failed")

    return state


# ══════════════════════════════════════════════════════════════════
# 에이전트 5: 판매 후 최적화 에이전트
# 판단: sale_status == "unsold"면 price_optimization_tool 호출
#       sold면 아무것도 안 함
# ══════════════════════════════════════════════════════════════════

def post_sale_optimization_node(state: SellerCopilotState) -> SellerCopilotState:
    _log(state, "agent5:post_sale_optimization:start")

    sale_status = state.get("sale_status")
    canonical = state.get("canonical_listing") or {}
    product = state.get("confirmed_product") or {}

    if sale_status == "sold":
        _log(state, "agent5:sold → no action needed")
        state["status"] = "completed"
        return state

    if sale_status != "unsold":
        _log(state, f"agent5:sale_status={sale_status} → awaiting input")
        state["status"] = "awaiting_sale_status_update"
        return state

    # ── 도구 선택: 가격 최적화 ────────────────────────────────────
    _log(state, "agent5:selecting_tool:price_optimization_tool")
    from app.tools.agentic_tools import price_optimization_tool

    # followup_due_at에서 경과 일수 계산
    days_listed = 7  # 기본값
    followup_str = state.get("followup_due_at")
    if followup_str:
        try:
            followup_dt = datetime.fromisoformat(followup_str)
            days_listed = max(1, (datetime.now(timezone.utc) - followup_dt).days + 7)
        except Exception:
            pass

    opt_call = _run_async(price_optimization_tool(
        canonical_listing=canonical,
        confirmed_product=product,
        sale_status=sale_status,
        days_listed=days_listed,
    ))
    _record_tool_call(state, opt_call)

    opt_output = opt_call.get("output") or {}
    if opt_output.get("type"):
        state["optimization_suggestion"] = opt_output
        state["status"] = "optimization_suggested"
        _log(state, f"agent5:suggestion type={opt_output.get('type')} price={opt_output.get('suggested_price')}")
    else:
        state["status"] = "awaiting_sale_status_update"
        _log(state, "agent5:no_suggestion_generated")

    return state


def publish_node(state: SellerCopilotState) -> SellerCopilotState:
    """
    패키지를 실제 플랫폼에 게시한다.
    성공/실패 결과를 state["publish_results"]에 기록.
    실패가 있으면 recovery_node로 라우팅.
    """
    _log(state, "publish_node:start")

    platform_packages = state.get("platform_packages") or {}
    if not platform_packages:
        _record_error(state, "publish_node", "platform_packages 없음")
        state["status"] = "failed"
        return state

    from app.services.publish_service import PublishService
    service = PublishService()
    publish_results = {}

    for platform, payload in platform_packages.items():
        _log(state, f"publish_node:publishing platform={platform}")
        try:
            result = _run_async(service.publish(platform=platform, payload=payload))
            publish_results[platform] = {
                "success": result.success,
                "external_url": result.external_url,
                "external_listing_id": result.external_listing_id,
                "error_code": result.error_code,
                "error_message": result.error_message,
                "evidence_path": result.evidence_path,
            }
            if result.success:
                _log(state, f"publish_node:success platform={platform} url={result.external_url}")
            else:
                _log(state, f"publish_node:failed platform={platform} error={result.error_message}")
        except Exception as e:
            _record_error(state, "publish_node", f"{platform}: {e}")
            publish_results[platform] = {
                "success": False,
                "error_code": "exception",
                "error_message": str(e),
            }

    state["publish_results"] = publish_results
    any_failed = any(not r.get("success") for r in publish_results.values())

    if any_failed:
        state["checkpoint"] = "D_publish_failed"
        state["status"] = "publishing_failed"
        _log(state, "publish_node:done some_failures=True → routing to recovery")
    else:
        state["checkpoint"] = "D_complete"
        state["status"] = "published"
        _log(state, "publish_node:done all_success=True")

    return state


# ══════════════════════════════════════════════════════════════════
# 패키지 빌더 (에이전트 아님 — 확정된 결과를 플랫폼 포맷으로 변환)
# ══════════════════════════════════════════════════════════════════

def package_builder_node(state: SellerCopilotState) -> SellerCopilotState:
    _log(state, "package_builder:start")

    canonical = state.get("canonical_listing") or {}
    title = canonical.get("title") or ""
    description = canonical.get("description") or ""
    price = _safe_int(canonical.get("price"), 0)
    images = canonical.get("images") or []
    product = canonical.get("product") or state.get("confirmed_product") or {}
    category = product.get("category") or ""

    selected = state.get("selected_platforms") or ["bunjang", "joongna"]
    packages = {}

    for platform in selected:
        if platform == "bunjang":
            platform_price = price + 10000 if price > 0 else 0
        elif platform == "daangn":
            platform_price = max(price - 4000, 0) if price > 0 else 0
        else:
            platform_price = price

        packages[platform] = {
            "title": title,
            "body": description,
            "price": platform_price,
            "images": images,
            "category": category,
        }

    state["platform_packages"] = packages
    state["checkpoint"] = "C_prepared"
    state["status"] = "awaiting_publish_approval"
    _log(state, f"package_builder:done platforms={list(packages.keys())}")
    return state
