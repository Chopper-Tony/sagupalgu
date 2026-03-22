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

    # 이미 주입된 market_context가 있으면 스킵 (SessionService 경로)
    if state.get("market_context") and _safe_int(
        (state["market_context"] or {}).get("sample_count"), 0
    ) > 0:
        _log(state, "agent2:market_intelligence:using_precomputed_context")
        state["checkpoint"] = "B_market_complete"
        return state

    # ── 도구 1 호출: 시세 수집 ──────────────────────────────────
    from app.tools.agentic_tools import market_crawl_tool, rag_price_tool

    _log(state, "agent2:selecting_tool:market_crawl_tool")
    crawl_result = _run_async(market_crawl_tool(product))
    _record_tool_call(state, crawl_result)

    crawl_output = crawl_result.get("output") or {}
    sample_count = _safe_int(crawl_output.get("sample_count"), 0)

    # ── 에이전트 판단: 표본 부족하면 RAG로 보완 ──────────────────
    rag_output = {}
    if sample_count < 3:
        _log(state, f"agent2:sample_count={sample_count}<3 → selecting_tool:rag_price_tool")
        rag_result = _run_async(rag_price_tool(product))
        _record_tool_call(state, rag_result)
        rag_output = rag_result.get("output") or {}
    else:
        _log(state, f"agent2:sample_count={sample_count} sufficient, skipping rag")

    # ── 결과 통합 ────────────────────────────────────────────────
    state["market_context"] = MarketContext(
        price_band=crawl_output.get("price_band") or [],
        median_price=crawl_output.get("median_price"),
        sample_count=sample_count,
        crawler_sources=crawl_output.get("crawler_sources") or [],
    )

    if rag_output.get("rag_summary"):
        meta = state.get("workflow_meta") or {}
        meta["rag_summary"] = rag_output["rag_summary"]

    state["checkpoint"] = "B_market_complete"
    state["status"] = "market_analyzing"
    _log(state, f"agent2:market_intelligence:done sample_count={sample_count}")
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

    # ── 에이전트 판단: 재작성 요청이 있는가? ─────────────────────
    if rewrite_instruction and existing_listing:
        _log(state, f"agent3:selecting_tool:rewrite_listing_tool instruction={rewrite_instruction[:30]}")
        from app.tools.agentic_tools import rewrite_listing_tool

        result = _run_async(rewrite_listing_tool(
            canonical_listing=existing_listing,
            rewrite_instruction=rewrite_instruction,
            confirmed_product=product,
            market_context=market_context,
            strategy=strategy,
        ))
        _record_tool_call(state, result)

        if result.get("success") and result.get("output"):
            state["canonical_listing"] = result["output"]
            state["rewrite_instruction"] = None  # 처리 완료 후 초기화
            _log(state, "agent3:rewrite:success")
        else:
            _log(state, f"agent3:rewrite:failed error={result.get('error')}")
            # 실패해도 기존 listing 유지
    else:
        # ── 신규 생성: ListingService 직접 호출 ──────────────────
        _log(state, "agent3:selecting_tool:listing_service (new generation)")
        try:
            from app.services.listing_service import ListingService

            svc = ListingService()
            image_paths = state.get("image_paths") or []
            result = _run_async(svc.build_canonical_listing(
                confirmed_product=product,
                market_context=market_context,
                strategy=strategy,
                image_paths=image_paths,
            ))
            state["canonical_listing"] = result
            _log(state, "agent3:new_listing:success")
        except Exception as e:
            _record_error(state, "copywriting_node", str(e))
            # fallback: 템플릿 기반 생성
            _log(state, f"agent3:llm_failed fallback to template error={e}")
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
    실패 원인을 진단하고, 자동 복구 가능한 경우 재시도 신호를 보낸다.
    """
    _log(state, "agent4:recovery:start")

    from app.tools.agentic_tools import diagnose_publish_failure_tool, discord_alert_tool

    publish_results = state.get("publish_results") or {}
    diagnostics = []
    any_auto_recoverable = False

    for platform, result in publish_results.items():
        if result.get("success"):
            continue

        # ── 도구 선택: 장애 진단 ──────────────────────────────────
        _log(state, f"agent4:selecting_tool:diagnose_publish_failure platform={platform}")
        diag_call = diagnose_publish_failure_tool(
            platform=platform,
            error_code=result.get("error_code", "unknown"),
            error_message=result.get("error_message", ""),
        )
        _record_tool_call(state, diag_call)
        diag = diag_call.get("output") or {}
        diagnostics.append(diag)

        if diag.get("auto_recoverable"):
            any_auto_recoverable = True

        # ── 도구 선택: Discord 알림 (항상 호출) ─────────────────
        _log(state, "agent4:selecting_tool:discord_alert_tool")
        alert_call = _run_async(discord_alert_tool(
            message=(
                f"[{platform}] 게시 실패\n"
                f"원인: {diag.get('likely_cause')}\n"
                f"제안: {diag.get('patch_suggestion')}\n"
                f"자동복구: {diag.get('auto_recoverable')}"
            ),
            session_id=state.get("session_id", "unknown"),
            level="error",
        ))
        _record_tool_call(state, alert_call)

    state["publish_diagnostics"] = diagnostics
    state["should_retry_publish"] = any_auto_recoverable  # 라우터가 읽는 신호

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
