"""
agentic_tools.py 공개 계약 테스트 (순수 단위)

공개 심볼이 항상 존재하는지, _impl 심볼이 노출되지 않는지 잠근다.
"""
import pytest

import app.tools.agentic_tools as facade

# ── 공개 심볼 목록 ────────────────────────────────────────────────

PUBLIC_SYMBOLS = [
    # Agent 2
    "lc_market_crawl_tool",
    "lc_rag_price_tool",
    "market_crawl_tool",
    "rag_price_tool",
    # Agent 3
    "lc_generate_listing_tool",
    "lc_rewrite_listing_tool",
    "rewrite_listing_tool",
    # Agent 4
    "lc_diagnose_publish_failure_tool",
    "lc_auto_patch_tool",
    "lc_discord_alert_tool",
    "diagnose_publish_failure_tool",
    "auto_patch_tool",
    "discord_alert_tool",
    # Agent 5
    "price_optimization_tool",
    # 공통 헬퍼
    "_make_tool_call",
    "_extract_json",
]

# ── 노출 금지 심볼 (구현 내부) ─────────────────────────────────────

PRIVATE_IMPL_SYMBOLS = [
    "_market_crawl_impl",
    "_rag_price_impl",
    "_rewrite_listing_impl",
]


@pytest.mark.unit
@pytest.mark.parametrize("symbol", PUBLIC_SYMBOLS)
def test_public_symbol_exists(symbol):
    assert hasattr(facade, symbol), f"agentic_tools에 공개 심볼 '{symbol}'이 없습니다"


@pytest.mark.unit
@pytest.mark.parametrize("symbol", PRIVATE_IMPL_SYMBOLS)
def test_impl_symbol_not_exposed(symbol):
    assert not hasattr(facade, symbol), (
        f"agentic_tools에 내부 구현 심볼 '{symbol}'이 노출되어 있습니다 — facade에서 제거하세요"
    )
