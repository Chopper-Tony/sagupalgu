"""
listing_prompt 확장 함수 unit 테스트.

M32에서 추가된 build_tool_calls_context, build_rewrite_context,
build_pricing_strategy 순수 함수를 검증한다.
"""
import pytest

from app.services.listing_prompt import (
    build_pricing_strategy,
    build_rewrite_context,
    build_tool_calls_context,
)


class TestBuildToolCallsContext:

    @pytest.mark.unit
    def test_empty_list_returns_empty_string(self):
        assert build_tool_calls_context([]) == ""

    @pytest.mark.unit
    def test_none_returns_empty_string(self):
        assert build_tool_calls_context(None) == ""

    @pytest.mark.unit
    def test_formats_success_and_failure(self):
        calls = [
            {"tool_name": "crawl", "success": True},
            {"tool_name": "rag", "success": False},
        ]
        result = build_tool_calls_context(calls)
        assert "crawl: success" in result
        assert "rag: failed" in result

    @pytest.mark.unit
    def test_missing_tool_name_defaults_to_unknown(self):
        calls = [{"success": True}]
        result = build_tool_calls_context(calls)
        assert "unknown: success" in result


class TestBuildRewriteContext:

    @pytest.mark.unit
    def test_includes_existing_title(self):
        listing = {"title": "기존 제목", "description": "기존 설명"}
        result = build_rewrite_context(listing, "더 짧게")
        assert "기존 제목" in result

    @pytest.mark.unit
    def test_includes_instruction(self):
        listing = {"title": "제목", "description": "설명"}
        result = build_rewrite_context(listing, "가격 강조해주세요")
        assert "가격 강조해주세요" in result

    @pytest.mark.unit
    def test_description_truncated_to_200(self):
        listing = {"title": "제목", "description": "A" * 500}
        result = build_rewrite_context(listing, "수정")
        # 설명이 200자로 잘렸는지 확인 (원문 500자인데 출력에서 200자만)
        assert "A" * 201 not in result

    @pytest.mark.unit
    def test_missing_fields_use_defaults(self):
        result = build_rewrite_context({}, "수정해주세요")
        assert "수정해주세요" in result


class TestBuildPricingStrategy:

    @pytest.mark.unit
    def test_positive_median_applies_discount(self):
        result = build_pricing_strategy(100000)
        assert result["recommended_price"] == 97000
        assert result["goal"] == "balanced"

    @pytest.mark.unit
    def test_goal_fast_sell_applies_larger_discount(self):
        result = build_pricing_strategy(100000, goal="fast_sell")
        assert result["recommended_price"] == 90000
        assert result["goal"] == "fast_sell"
        assert result["negotiation_policy"] == "negotiation welcome, fast deal priority"

    @pytest.mark.unit
    def test_goal_profit_max_applies_premium(self):
        result = build_pricing_strategy(100000, goal="profit_max")
        assert result["recommended_price"] == 105000
        assert result["goal"] == "profit_max"
        assert result["negotiation_policy"] == "firm price, value justified"

    @pytest.mark.unit
    def test_zero_median_gives_zero_price(self):
        result = build_pricing_strategy(0)
        assert result["recommended_price"] == 0

    @pytest.mark.unit
    def test_negative_median_gives_zero_price(self):
        result = build_pricing_strategy(-50000)
        assert result["recommended_price"] == 0

    @pytest.mark.unit
    def test_large_median_scales_correctly(self):
        result = build_pricing_strategy(1000000)
        assert result["recommended_price"] == 970000

    @pytest.mark.unit
    def test_always_includes_negotiation_policy(self):
        result = build_pricing_strategy(500000)
        assert "negotiation_policy" in result
