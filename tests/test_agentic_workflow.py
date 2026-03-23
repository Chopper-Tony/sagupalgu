"""
사구팔구 Agentic Workflow 테스트 스위트

테스트 범위:
1. 에이전트별 도구 선택 자율성
2. LangGraph 조건 분기 (validation 재시도, clarification 분기)
3. 검증·복구 에이전트 (Agent 4) 진단 로직
4. 판매 후 최적화 에이전트 (Agent 5)
5. 판매글 재작성 tool 트리거
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Any, Dict


# ─────────────────────────────────────────────────────────────────
# 픽스처
# ─────────────────────────────────────────────────────────────────

@pytest.fixture
def confirmed_product():
    return {
        "brand": "Apple",
        "model": "iPhone 15 Pro",
        "category": "smartphone",
        "confidence": 0.92,
        "source": "vision",
        "storage": "256GB",
    }


@pytest.fixture
def market_context():
    return {
        "price_band": [900000, 1100000],
        "median_price": 980000,
        "sample_count": 12,
        "crawler_sources": ["번개장터", "중고나라"],
    }


@pytest.fixture
def strategy():
    return {
        "goal": "fast_sell",
        "recommended_price": 950600,
        "negotiation_policy": "small negotiation allowed",
    }


@pytest.fixture
def canonical_listing(confirmed_product, strategy):
    return {
        "title": "Apple iPhone 15 Pro 256GB 판매합니다",
        "description": "깨끗하게 사용했습니다. 실사진 참고 부탁드립니다. 빠른 거래 원합니다.",
        "tags": ["iPhone15Pro", "Apple", "smartphone"],
        "price": 950600,
        "images": ["path/to/image.jpg"],
        "strategy": "fast_sell",
        "product": confirmed_product,
    }


@pytest.fixture
def base_state(confirmed_product, market_context, strategy, canonical_listing):
    """그래프 실행 중간 단계 상태"""
    return {
        "session_id": "test-session-001",
        "status": "product_confirmed",
        "checkpoint": "A_complete",
        "schema_version": 2,
        "image_paths": ["path/to/image.jpg"],
        "selected_platforms": ["bunjang", "joongna"],
        "user_product_input": {},
        "product_candidates": [],
        "confirmed_product": confirmed_product,
        "analysis_source": "vision",
        "needs_user_input": False,
        "clarification_prompt": None,
        "search_queries": [],
        "market_context": market_context,
        "strategy": strategy,
        "canonical_listing": canonical_listing,
        "platform_packages": {},
        "rewrite_instruction": None,
        "validation_passed": False,
        "validation_result": {"passed": False, "issues": []},
        "validation_retry_count": 0,
        "tool_calls": [],
        "publish_diagnostics": [],
        "publish_retry_count": 0,
        "publish_results": {},
        "sale_status": None,
        "optimization_suggestion": None,
        "followup_due_at": None,
        "error_history": [],
        "last_error": None,
        "debug_logs": [],
    }


# ─────────────────────────────────────────────────────────────────
# 1. 에이전트 1: 상품 식별 — 분기 테스트
# ─────────────────────────────────────────────────────────────────

class TestProductIdentityAgent:

    def test_user_input_확정(self):
        """사용자 입력이 있으면 도구 없이 바로 confirmed_product 설정"""
        from app.graph.seller_copilot_nodes import product_identity_node

        state = {
            "user_product_input": {"brand": "Samsung", "model": "Galaxy S24", "category": "smartphone"},
            "product_candidates": [],
            "tool_calls": [], "debug_logs": [], "error_history": [],
        }
        result = product_identity_node(state)

        assert result["confirmed_product"]["model"] == "Galaxy S24"
        assert result["confirmed_product"]["source"] == "user_input"
        assert result["needs_user_input"] is False
        assert result["checkpoint"] == "A_complete"

    def test_high_confidence_vision_확정(self):
        """Vision confidence >= 0.6이면 자동 확정"""
        from app.graph.seller_copilot_nodes import product_identity_node

        state = {
            "user_product_input": {},
            "product_candidates": [
                {"brand": "Apple", "model": "iPhone 15", "category": "smartphone", "confidence": 0.91}
            ],
            "tool_calls": [], "debug_logs": [], "error_history": [],
        }
        result = product_identity_node(state)

        assert result["confirmed_product"]["model"] == "iPhone 15"
        assert result["needs_user_input"] is False

    def test_low_confidence_사용자입력요청(self):
        """confidence < 0.6이면 사용자 입력 요청으로 분기"""
        from app.graph.seller_copilot_nodes import product_identity_node

        state = {
            "user_product_input": {},
            "product_candidates": [
                {"brand": "Unknown", "model": "Unknown", "category": "unknown", "confidence": 0.3}
            ],
            "tool_calls": [], "debug_logs": [], "error_history": [],
        }
        result = product_identity_node(state)

        assert result["needs_user_input"] is True
        assert result["clarification_prompt"] is not None
        assert result["checkpoint"] == "A_needs_user_input"

    def test_empty_candidates_사용자입력요청(self):
        """candidates 없으면 사용자 입력 요청"""
        from app.graph.seller_copilot_nodes import product_identity_node

        state = {
            "user_product_input": {},
            "product_candidates": [],
            "tool_calls": [], "debug_logs": [], "error_history": [],
        }
        result = product_identity_node(state)
        assert result["needs_user_input"] is True


# ─────────────────────────────────────────────────────────────────
# 2. 에이전트 2: 시세 분석 — 도구 선택 자율성
# ─────────────────────────────────────────────────────────────────

class TestMarketIntelligenceAgent:

    @pytest.mark.asyncio
    async def test_충분한표본_rag_스킵(self, confirmed_product):
        """sample_count >= 3이면 RAG 도구를 호출하지 않는다"""
        from app.graph.seller_copilot_nodes import market_intelligence_node

        crawl_output = {
            "median_price": 980000, "price_band": [900000, 1100000],
            "sample_count": 12, "crawler_sources": ["번개장터"],
        }

        with patch("app.tools.agentic_tools.market_crawl_tool",
                   new_callable=AsyncMock) as mock_crawl, \
             patch("app.tools.agentic_tools.rag_price_tool",
                   new_callable=AsyncMock) as mock_rag:

            mock_crawl.return_value = {
                "tool_name": "market_crawl_tool", "output": crawl_output, "success": True
            }

            state = {
                "confirmed_product": confirmed_product,
                "market_context": None,
                "tool_calls": [], "debug_logs": [], "error_history": [],
            }

            # _run_async를 우회하기 위해 직접 AsyncMock 결과 주입
            with patch("app.graph.nodes.market_agent._run_async", side_effect=lambda c: mock_crawl.return_value):
                result = market_intelligence_node(state)

            # RAG는 호출되지 않아야 함
            mock_rag.assert_not_called()
            assert result["market_context"]["sample_count"] == 12

    def test_기존_market_context_스킵(self, confirmed_product, market_context):
        """이미 market_context가 있으면 도구 호출 없이 스킵"""
        from app.graph.seller_copilot_nodes import market_intelligence_node

        state = {
            "confirmed_product": confirmed_product,
            "market_context": market_context,  # 이미 있음
            "tool_calls": [], "debug_logs": [], "error_history": [],
        }

        with patch("app.tools.agentic_tools.market_crawl_tool") as mock_crawl:
            result = market_intelligence_node(state)
            mock_crawl.assert_not_called()

        assert result["checkpoint"] == "B_market_complete"

    def test_확정상품없으면_실패(self):
        """confirmed_product 없으면 status=failed"""
        from app.graph.seller_copilot_nodes import market_intelligence_node

        state = {
            "confirmed_product": None,
            "market_context": None,
            "tool_calls": [], "debug_logs": [], "error_history": [],
        }
        result = market_intelligence_node(state)
        assert result["status"] == "failed"
        assert result["last_error"] is not None


# ─────────────────────────────────────────────────────────────────
# 3. 에이전트 3: 판매글 생성 — rewrite 도구 선택
# ─────────────────────────────────────────────────────────────────

class TestCopywritingAgent:

    def test_재작성지시_있으면_rewrite_tool_호출(self, base_state):
        """rewrite_instruction이 있으면 LLM이 lc_rewrite_listing_tool을 자율 선택한다 (ReAct)"""
        import json
        from app.graph.seller_copilot_nodes import copywriting_node

        state = {**base_state, "rewrite_instruction": "더 신뢰감 있게 작성해주세요"}
        rewritten = {**base_state["canonical_listing"], "title": "Apple iPhone 15 Pro 256GB 믿을 수 있는 판매자"}

        # ReAct agent가 반환하는 messages 구조: LLM tool_call → ToolMessage(JSON 결과)
        llm_msg = MagicMock()
        llm_msg.tool_calls = [{"name": "lc_rewrite_listing_tool", "args": {"rewrite_instruction": "더 신뢰감 있게"}}]
        llm_msg.content = ""

        tool_msg = MagicMock()
        tool_msg.tool_calls = []
        tool_msg.content = json.dumps(rewritten, ensure_ascii=False)

        mock_agent_result = {"messages": [llm_msg, tool_msg]}

        with patch("app.graph.nodes.copywriting_agent._build_react_llm", return_value=MagicMock()):
            with patch("app.graph.nodes.copywriting_agent._run_async", return_value=mock_agent_result):
                result = copywriting_node(state)

        assert result["canonical_listing"]["title"] == rewritten["title"]
        assert result["rewrite_instruction"] is None  # 처리 후 초기화

    def test_재작성지시_없으면_신규생성(self, base_state):
        """rewrite_instruction 없으면 ListingService로 신규 생성"""
        from app.graph.seller_copilot_nodes import copywriting_node

        state = {**base_state, "canonical_listing": None, "rewrite_instruction": None}
        new_listing = {"title": "신규 생성 제목", "description": "신규 설명", "price": 950000, "tags": [], "images": []}

        with patch("app.services.listing_service.ListingService") as MockSvc:
            instance = MockSvc.return_value
            instance.build_canonical_listing = AsyncMock(return_value=new_listing)
            with patch("app.graph.seller_copilot_nodes._run_async", return_value=new_listing):
                result = copywriting_node(state)

        assert result["status"] == "draft_generated"
        assert result["checkpoint"] == "B_draft_complete"

    def test_llm_실패시_템플릿_fallback(self, base_state):
        """LLM 호출 실패 시 템플릿 기반으로 fallback"""
        from app.graph.seller_copilot_nodes import copywriting_node

        state = {**base_state, "canonical_listing": None, "rewrite_instruction": None}

        with patch("app.graph.seller_copilot_nodes._run_async", side_effect=Exception("LLM timeout")):
            with patch("app.services.listing_service.ListingService"):
                result = copywriting_node(state)

        # fallback listing이 생성되어야 함
        assert result["canonical_listing"] is not None
        assert result["status"] == "draft_generated"


# ─────────────────────────────────────────────────────────────────
# 4. 에이전트 4: 검증 — retry 루프
# ─────────────────────────────────────────────────────────────────

class TestValidationAgent:

    def test_정상_listing_통과(self, base_state):
        from app.graph.seller_copilot_nodes import validation_node

        result = validation_node(base_state)
        assert result["validation_passed"] is True
        assert result["checkpoint"] == "B_complete"

    def test_짧은제목_실패(self, base_state):
        from app.graph.seller_copilot_nodes import validation_node

        state = {**base_state}
        state["canonical_listing"] = {**base_state["canonical_listing"], "title": "짧"}
        result = validation_node(state)

        assert result["validation_passed"] is False
        assert result["validation_retry_count"] == 1
        error_codes = [i["code"] for i in result["validation_result"]["issues"]]
        assert "title_too_short" in error_codes

    def test_refinement_후_재검증(self, base_state):
        """refinement_node가 수정한 내용이 재검증에서 통과하는지"""
        from app.graph.seller_copilot_nodes import refinement_node, validation_node

        state = {**base_state}
        state["canonical_listing"] = {
            **base_state["canonical_listing"],
            "description": "짧음",  # 너무 짧음
            "price": 0,              # 가격 없음
        }

        # refinement 실행
        refined = refinement_node(state)
        assert len(refined["canonical_listing"]["description"]) >= 20
        assert refined["canonical_listing"]["price"] > 0  # 시세에서 자동 계산

        # 재검증
        validated = validation_node(refined)
        assert validated["validation_passed"] is True

    def test_최대재시도_초과시_통과처리(self):
        """validation_retry_count >= MAX면 강제 통과"""
        from app.graph.seller_copilot_graph import route_after_validation

        state = {
            "validation_passed": False,
            "validation_retry_count": 2,  # MAX = 2
        }
        result = route_after_validation(state)
        assert result == "package_builder_node"


# ─────────────────────────────────────────────────────────────────
# 5. 에이전트 4: 복구 — 진단 + Discord 알림
# ─────────────────────────────────────────────────────────────────

class TestRecoveryAgent:

    def test_네트워크오류_자동복구가능(self):
        from app.tools.agentic_tools import diagnose_publish_failure_tool

        result = diagnose_publish_failure_tool(
            platform="bunjang",
            error_code="publish_exception",
            error_message="Connection timeout occurred",
        )
        diag = result["output"]
        assert diag["likely_cause"] == "network"
        assert diag["auto_recoverable"] is True

    def test_로그인만료_자동복구불가(self):
        from app.tools.agentic_tools import diagnose_publish_failure_tool

        result = diagnose_publish_failure_tool(
            platform="joongna",
            error_code="auth_error",
            error_message="Session expired, please login again",
        )
        diag = result["output"]
        assert diag["likely_cause"] == "login_expired"
        assert diag["auto_recoverable"] is False

    def test_콘텐츠정책위반_자동복구불가(self):
        from app.tools.agentic_tools import diagnose_publish_failure_tool

        result = diagnose_publish_failure_tool(
            platform="bunjang",
            error_code="content_rejected",
            error_message="Content policy violation detected",
        )
        diag = result["output"]
        assert diag["likely_cause"] == "content_policy"
        assert diag["auto_recoverable"] is False

    def test_recovery_node_실패시_tool_기록(self, base_state):
        """recovery_node 실행 시 tool_calls에 진단 기록이 쌓인다"""
        from app.graph.seller_copilot_nodes import recovery_node

        state = {
            **base_state,
            "publish_results": {
                "bunjang": {
                    "success": False,
                    "error_code": "publish_exception",
                    "error_message": "Connection timeout",
                }
            },
        }

        with patch("app.tools.agentic_tools.discord_alert_tool", new_callable=AsyncMock) as mock_discord:
            mock_discord.return_value = {"tool_name": "discord_alert_tool", "output": {"sent": False}, "success": True}
            with patch("app.graph.seller_copilot_nodes._run_async", return_value={
                "tool_name": "discord_alert_tool", "output": {"sent": False}, "success": True
            }):
                result = recovery_node(state)

        # tool_calls에 진단 기록이 있어야 함
        assert len(result["tool_calls"]) >= 1
        tool_names = [c["tool_name"] for c in result["tool_calls"]]
        assert "diagnose_publish_failure_tool" in tool_names

    def test_recovery_재시도횟수_초과(self, base_state):
        """publish_retry_count >= 2면 publishing_failed로 전환"""
        from app.graph.seller_copilot_nodes import recovery_node

        state = {
            **base_state,
            "publish_retry_count": 2,
            "publish_results": {
                "bunjang": {"success": False, "error_code": "unknown", "error_message": "unknown error"}
            },
        }

        with patch("app.graph.seller_copilot_nodes._run_async", return_value={
            "tool_name": "discord_alert_tool", "output": {"sent": False}, "success": True
        }):
            result = recovery_node(state)

        assert result["status"] == "publishing_failed"
        assert result["checkpoint"] == "D_publish_failed"


# ─────────────────────────────────────────────────────────────────
# 6. 에이전트 5: 판매 후 최적화
# ─────────────────────────────────────────────────────────────────

class TestPostSaleOptimizationAgent:

    @pytest.mark.asyncio
    async def test_미판매_가격인하_제안(self, confirmed_product, canonical_listing):
        from app.tools.agentic_tools import price_optimization_tool

        result = await price_optimization_tool(
            canonical_listing=canonical_listing,
            confirmed_product=confirmed_product,
            sale_status="unsold",
            days_listed=7,
        )
        output = result["output"]
        assert output["type"] == "price_drop"
        assert output["suggested_price"] < canonical_listing["price"]
        assert output["urgency"] == "medium"

    @pytest.mark.asyncio
    async def test_장기미판매_높은긴급도(self, confirmed_product, canonical_listing):
        from app.tools.agentic_tools import price_optimization_tool

        result = await price_optimization_tool(
            canonical_listing=canonical_listing,
            confirmed_product=confirmed_product,
            sale_status="unsold",
            days_listed=15,
        )
        output = result["output"]
        assert output["urgency"] == "high"
        # 10% 인하
        assert output["suggested_price"] <= int(canonical_listing["price"] * 0.91)

    @pytest.mark.asyncio
    async def test_판매완료_제안없음(self, confirmed_product, canonical_listing):
        from app.tools.agentic_tools import price_optimization_tool

        result = await price_optimization_tool(
            canonical_listing=canonical_listing,
            confirmed_product=confirmed_product,
            sale_status="sold",
            days_listed=3,
        )
        assert result["output"].get("suggestion") is None or result["output"].get("type") is None

    def test_판매완료_노드_상태전환(self, base_state):
        from app.graph.seller_copilot_nodes import post_sale_optimization_node

        state = {**base_state, "sale_status": "sold"}
        result = post_sale_optimization_node(state)
        assert result["status"] == "completed"

    def test_미판매_최적화노드_실행(self, base_state, canonical_listing):
        from app.graph.seller_copilot_nodes import post_sale_optimization_node

        state = {**base_state, "sale_status": "unsold", "canonical_listing": canonical_listing}
        opt_output = {
            "type": "price_drop", "current_price": 950600,
            "suggested_price": 903000, "reason": "7일 미판매", "urgency": "medium"
        }
        mock_result = {"tool_name": "price_optimization_tool", "output": opt_output, "success": True}

        with patch("app.graph.seller_copilot_nodes._run_async", return_value=mock_result):
            result = post_sale_optimization_node(state)

        assert result["optimization_suggestion"]["type"] == "price_drop"
        assert result["status"] == "optimization_suggested"
        # tool_calls에 기록되어야 함
        assert any(c["tool_name"] == "price_optimization_tool" for c in result["tool_calls"])


# ─────────────────────────────────────────────────────────────────
# 7. 도구 자율 선택 — tool_calls 추적
# ─────────────────────────────────────────────────────────────────

class TestToolCallTracking:

    def test_tool_calls_누적(self, base_state):
        """각 에이전트가 도구를 호출하면 tool_calls에 기록이 쌓인다"""
        from app.graph.seller_copilot_nodes import validation_node, refinement_node

        state = {**base_state}
        state["canonical_listing"] = {
            **base_state["canonical_listing"],
            "description": "짧음",
            "price": 0,
        }

        after_validation = validation_node(state)
        after_refinement = refinement_node(after_validation)
        after_revalidation = validation_node(after_refinement)

        # debug_logs에 각 에이전트 실행 흔적이 남아야 함
        all_logs = " ".join(after_revalidation.get("debug_logs") or [])
        assert "agent4:validation" in all_logs
        assert "agent4:refinement" in all_logs

    def test_market_intelligence_tool_calls_기록(self, confirmed_product):
        """market_intelligence_node가 도구 호출 결과를 tool_calls에 기록한다"""
        from app.graph.seller_copilot_nodes import market_intelligence_node

        crawl_output = {
            "median_price": 980000, "price_band": [900000, 1100000],
            "sample_count": 10, "crawler_sources": ["번개장터"],
        }
        mock_result = {"tool_name": "market_crawl_tool", "output": crawl_output, "success": True}

        state = {
            "confirmed_product": confirmed_product,
            "market_context": None,
            "tool_calls": [], "debug_logs": [], "error_history": [],
        }

        with patch("app.graph.seller_copilot_nodes._run_async", return_value=mock_result):
            result = market_intelligence_node(state)

        assert len(result["tool_calls"]) >= 1
        assert result["tool_calls"][0]["tool_name"] == "market_crawl_tool"
        assert result["tool_calls"][0]["success"] is True


# ─────────────────────────────────────────────────────────────────
# 8. 패키지 빌더
# ─────────────────────────────────────────────────────────────────

class TestPackageBuilder:

    def test_플랫폼별_가격_차등(self, base_state):
        from app.graph.seller_copilot_nodes import package_builder_node

        state = {**base_state, "selected_platforms": ["bunjang", "joongna", "daangn"]}
        result = package_builder_node(state)

        base_price = base_state["canonical_listing"]["price"]
        assert result["platform_packages"]["bunjang"]["price"] == base_price + 10000
        assert result["platform_packages"]["joongna"]["price"] == base_price
        assert result["platform_packages"]["daangn"]["price"] == max(base_price - 4000, 0)

    def test_패키지_필수필드(self, base_state):
        from app.graph.seller_copilot_nodes import package_builder_node

        result = package_builder_node(base_state)
        for platform, pkg in result["platform_packages"].items():
            assert "title" in pkg
            assert "body" in pkg
            assert "price" in pkg
            assert "images" in pkg


# ─────────────────────────────────────────────────────────────────
# 9. 전체 graph 라우팅 통합 테스트
# ─────────────────────────────────────────────────────────────────

class TestGraphRouting:

    def test_needs_user_input_clarification으로_분기(self):
        from app.graph.seller_copilot_graph import route_after_product_identity

        state = {"needs_user_input": True}
        assert route_after_product_identity(state) == "clarification_node"

    def test_confirmed_product_market으로_분기(self):
        from app.graph.seller_copilot_graph import route_after_product_identity

        state = {"needs_user_input": False}
        assert route_after_product_identity(state) == "market_intelligence_node"

    def test_validation_passed_package로_분기(self):
        from app.graph.seller_copilot_graph import route_after_validation

        state = {"validation_passed": True, "validation_retry_count": 0}
        assert route_after_validation(state) == "package_builder_node"

    def test_validation_failed_refinement으로_분기(self):
        from app.graph.seller_copilot_graph import route_after_validation

        state = {"validation_passed": False, "validation_retry_count": 0}
        assert route_after_validation(state) == "refinement_node"

    def test_validation_재시도초과_강제통과(self):
        from app.graph.seller_copilot_graph import route_after_validation

        state = {"validation_passed": False, "validation_retry_count": 2}
        assert route_after_validation(state) == "package_builder_node"
