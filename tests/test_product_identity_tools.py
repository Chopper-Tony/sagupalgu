"""
PR4-2 신규 툴 3개 단위 테스트.

스코프:
  - lc_image_reanalyze_tool (focus 검증, 캐시, fallback)
  - lc_rag_product_catalog_tool (flag off, no api key, RPC 호출 위임)
  - lc_ask_user_clarification_tool (정상, 잘못된 input, 빈 questions)
  - budget guard helper

LLM/Supabase는 mock (CI 결정론).
"""
from __future__ import annotations

import json

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ── lc_image_reanalyze_tool ──────────────────────────────────────────


class TestImageReanalyze:
    @pytest.mark.unit
    async def test_invalid_focus_에러반환(self):
        from app.tools.product_identity_tools import lc_image_reanalyze_tool

        result = await lc_image_reanalyze_tool.ainvoke({
            "image_paths_json": "[]",
            "focus": "wrong_focus",
        })
        data = json.loads(result)
        assert "error" in data
        assert "valid" in data

    @pytest.mark.unit
    async def test_빈_image_paths_에러반환(self):
        from app.tools.product_identity_tools import lc_image_reanalyze_tool

        result = await lc_image_reanalyze_tool.ainvoke({
            "image_paths_json": "[]",
            "focus": "ocr",
        })
        data = json.loads(result)
        assert "error" in data
        assert "empty" in data["error"]

    @pytest.mark.unit
    async def test_invalid_image_paths_json_에러반환(self):
        from app.tools.product_identity_tools import lc_image_reanalyze_tool

        result = await lc_image_reanalyze_tool.ainvoke({
            "image_paths_json": "{not json",
            "focus": "spec",
        })
        data = json.loads(result)
        assert "error" in data

    @pytest.mark.integration
    async def test_정상_재분석_캐시_적중(self):
        """동일 image+focus 두 번 호출 시 두 번째는 캐시."""
        from app.tools import product_identity_tools

        # 캐시 격리
        product_identity_tools._reanalyze_cache.clear()

        mock_candidates = [
            {"brand": "Apple", "model": "iPhone 15", "category": "phone", "confidence": 0.85}
        ]
        with patch("app.services.product_service.ProductService") as MockSvc:
            MockSvc.return_value.identify_product = AsyncMock(return_value=mock_candidates)

            result1 = await product_identity_tools.lc_image_reanalyze_tool.ainvoke({
                "image_paths_json": '["img1.jpg"]',
                "focus": "ocr",
            })
            result2 = await product_identity_tools.lc_image_reanalyze_tool.ainvoke({
                "image_paths_json": '["img1.jpg"]',
                "focus": "ocr",
            })

        # 결과 동일
        assert result1 == result2
        # ProductService는 한 번만 호출 (두 번째는 캐시 hit)
        assert MockSvc.return_value.identify_product.call_count == 1

        data = json.loads(result1)
        assert data["confidence"] == pytest.approx(0.85)
        assert "ocr" in data["reanalysis_reason"]


# ── lc_rag_product_catalog_tool ──────────────────────────────────────


class TestRagProductCatalog:
    @pytest.mark.unit
    async def test_feature_flag_off면_cold_start(self):
        from app.tools.product_identity_tools import lc_rag_product_catalog_tool

        # Settings를 mock해서 enable_catalog_hybrid=False로 강제
        mock_settings = MagicMock()
        mock_settings.enable_catalog_hybrid = False
        with patch("app.core.config.get_settings", return_value=mock_settings):
            result = await lc_rag_product_catalog_tool.ainvoke({
                "brand_hint": "Apple",
                "model_hint": "iPhone 15",
            })

        data = json.loads(result)
        assert data["disabled_by_flag"] is True
        assert data["cold_start"] is True
        assert data["source_count"] == 0

    @pytest.mark.unit
    async def test_no_api_key면_cold_start(self):
        from app.tools.product_identity_tools import lc_rag_product_catalog_tool

        mock_settings = MagicMock()
        mock_settings.enable_catalog_hybrid = True
        mock_settings.openai_api_key = None
        with patch("app.core.config.get_settings", return_value=mock_settings):
            result = await lc_rag_product_catalog_tool.ainvoke({
                "brand_hint": "Apple",
                "model_hint": "iPhone 15",
            })

        data = json.loads(result)
        assert data["error"] == "no_api_key"
        assert data["cold_start"] is True

    @pytest.mark.integration
    async def test_정상_위임_hybrid_search(self):
        """flag on + api key 있으면 hybrid_search_catalog로 위임 + 결과 JSON으로 반환."""
        from app.tools import product_identity_tools

        mock_settings = MagicMock()
        mock_settings.enable_catalog_hybrid = True
        mock_settings.openai_api_key = "sk-test"

        catalog_result = {
            "matches": [{"brand": "Apple", "model": "iPhone 15", "similarity": 0.82, "source_type": "crawled"}],
            "top_match_confidence": 0.82,
            "source_count": 1,
            "cold_start": True,
            "cold_start_reason": "hit_count=1<3",
            "fallback_path": "vector",
            "source_breakdown": {"crawled": 1, "sell_session": 0, "manual": 0},
        }
        with patch("app.core.config.get_settings", return_value=mock_settings):
            with patch(
                "app.db.product_catalog_store.hybrid_search_catalog",
                new=AsyncMock(return_value=catalog_result),
            ):
                result = await product_identity_tools.lc_rag_product_catalog_tool.ainvoke({
                    "brand_hint": "Apple",
                    "model_hint": "iPhone 15",
                })

        data = json.loads(result)
        assert data["top_match_confidence"] == pytest.approx(0.82)
        assert data["fallback_path"] == "vector"


# ── lc_ask_user_clarification_tool ────────────────────────────────────


class TestAskUserClarification:
    @pytest.mark.unit
    def test_정상_questions_ack(self):
        from app.tools.product_identity_tools import lc_ask_user_clarification_tool

        questions = [
            {"id": "model_name", "question": "정확한 모델명?"},
            {"id": "color", "question": "색상은?"},
        ]
        result = lc_ask_user_clarification_tool.invoke({
            "questions_json": json.dumps(questions),
            "reason": "vision confidence 0.4",
        })
        data = json.loads(result)
        assert data["ack"] is True
        assert data["questions_count"] == 2
        assert "0.4" in data["reason"]

    @pytest.mark.unit
    def test_invalid_json_ack_False(self):
        from app.tools.product_identity_tools import lc_ask_user_clarification_tool

        result = lc_ask_user_clarification_tool.invoke({
            "questions_json": "not json",
            "reason": "x",
        })
        data = json.loads(result)
        assert data["ack"] is False

    @pytest.mark.unit
    def test_빈_questions_ack_False(self):
        from app.tools.product_identity_tools import lc_ask_user_clarification_tool

        result = lc_ask_user_clarification_tool.invoke({
            "questions_json": "[]",
            "reason": "x",
        })
        data = json.loads(result)
        assert data["ack"] is False

    @pytest.mark.unit
    def test_id_없는_question은_제외(self):
        from app.tools.product_identity_tools import lc_ask_user_clarification_tool

        questions = [
            {"question": "id 없음"},   # 무효
            {"id": "ok", "question": "정상"},
        ]
        result = lc_ask_user_clarification_tool.invoke({
            "questions_json": json.dumps(questions),
            "reason": "x",
        })
        data = json.loads(result)
        assert data["ack"] is True
        assert data["questions_count"] == 1


# ── Budget guard helper ──────────────────────────────────────────────


class TestBudgetGuard:
    @pytest.mark.unit
    def test_reanalyze_budget(self):
        from app.tools.product_identity_tools import (
            MAX_REANALYZE_CALLS, reanalyze_budget_exceeded,
        )
        assert reanalyze_budget_exceeded([]) is False
        assert reanalyze_budget_exceeded(["lc_image_reanalyze_tool"]) is False
        assert reanalyze_budget_exceeded(["lc_image_reanalyze_tool"] * MAX_REANALYZE_CALLS) is True
        assert reanalyze_budget_exceeded(["lc_image_reanalyze_tool"] * (MAX_REANALYZE_CALLS + 1)) is True

    @pytest.mark.unit
    def test_clarification_budget(self):
        from app.tools.product_identity_tools import (
            MAX_CLARIFICATION_CALLS, clarification_budget_exceeded,
        )
        assert clarification_budget_exceeded([]) is False
        assert clarification_budget_exceeded(["lc_ask_user_clarification_tool"] * MAX_CLARIFICATION_CALLS) is True

    @pytest.mark.unit
    def test_total_budget(self):
        """CTO PR4-2 #1: 전체 tool 호출 수 soft budget."""
        from app.tools.product_identity_tools import (
            MAX_TOTAL_TOOL_CALLS, total_budget_exceeded,
        )
        assert total_budget_exceeded([]) is False
        assert total_budget_exceeded(["a", "b", "c"]) is False  # < 4
        assert total_budget_exceeded(["a"] * MAX_TOTAL_TOOL_CALLS) is True
        assert total_budget_exceeded(["a"] * (MAX_TOTAL_TOOL_CALLS + 1)) is True


class TestFailureModeTaxonomy:
    """CTO PR4-2 #5: failure_mode enum (Literal) 검증."""

    @pytest.mark.unit
    def test_모든_failure_mode_literal에_정의됨(self):
        from typing import get_args
        from app.tools.product_identity_tools import ProductIdentityFailureMode

        modes = set(get_args(ProductIdentityFailureMode))
        # PR4-2에서 사용하는 모든 failure_mode는 enum에 들어있어야 함
        expected = {
            "react_exception",
            "product_identity_parse_error",
            "product_identity_contract_violation",
            "react_total_budget_exceeded",
            "clarify_forced_by_heuristic",
            "reanalyze_budget_exceeded",
            "max_clarify_calls_reached",
        }
        assert expected == modes, f"missing: {expected - modes}, extra: {modes - expected}"
