"""
PR4-3 — app/middleware/metrics.py 단위 테스트.

cold_start / fallback 알람 임계 (20% / 10%) + 카운터 누적 + 라벨 분기 검증.
"""
from __future__ import annotations

import pytest

from app.middleware.metrics import (
    ALERT_MIN_RUN_COUNT,
    PRODUCT_IDENTITY_COLD_START,
    PRODUCT_IDENTITY_FALLBACK,
    PRODUCT_IDENTITY_RUN,
    PRODUCT_IDENTITY_TOOL_CALL,
    compute_alert_status,
    emit_product_identity_run,
    get_registry,
)

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _reset_registry():
    get_registry().reset()
    yield
    get_registry().reset()


class TestEmitCounter:
    def test_run_total_누적(self):
        emit_product_identity_run(
            tool_calls_total=0, reanalyze_count=0, catalog_count=0, clarify_count=0,
            failure_mode=None, needs_user_input=False, confirmed_source="vision",
        )
        emit_product_identity_run(
            tool_calls_total=1, reanalyze_count=0, catalog_count=1, clarify_count=0,
            failure_mode=None, needs_user_input=False, confirmed_source="catalog",
        )
        snap = get_registry().snapshot()
        assert snap["counters"][f"{PRODUCT_IDENTITY_RUN}.total"] == 2

    def test_failure_mode_라벨링(self):
        emit_product_identity_run(
            tool_calls_total=0, reanalyze_count=0, catalog_count=0, clarify_count=0,
            failure_mode="react_exception",
            needs_user_input=False, confirmed_source="",
        )
        snap = get_registry().snapshot()
        assert snap["counters"][f"{PRODUCT_IDENTITY_FALLBACK}.total"] == 1
        assert snap["labeled"][PRODUCT_IDENTITY_FALLBACK]["react_exception"] == 1

    def test_cold_start_분리_누적(self):
        emit_product_identity_run(
            tool_calls_total=1, reanalyze_count=0, catalog_count=1, clarify_count=0,
            failure_mode=None, needs_user_input=False, confirmed_source="",
            cold_start=True,
        )
        snap = get_registry().snapshot()
        assert snap["counters"][f"{PRODUCT_IDENTITY_COLD_START}.total"] == 1

    def test_tool_call_라벨_누적(self):
        emit_product_identity_run(
            tool_calls_total=4, reanalyze_count=2, catalog_count=1, clarify_count=1,
            failure_mode=None, needs_user_input=True, confirmed_source="",
        )
        labeled = get_registry().snapshot()["labeled"][PRODUCT_IDENTITY_TOOL_CALL]
        assert labeled["reanalyze"] == 2
        assert labeled["catalog"] == 1
        assert labeled["clarify"] == 1


class TestAlertThreshold:
    def test_표본_부족시_insufficient_data(self):
        for _ in range(5):
            emit_product_identity_run(
                tool_calls_total=0, reanalyze_count=0, catalog_count=0, clarify_count=0,
                failure_mode=None, needs_user_input=False, confirmed_source="",
            )
        status = compute_alert_status()
        assert status["status"] == "insufficient_data"
        assert status["min_runs"] == ALERT_MIN_RUN_COUNT

    def test_cold_start_20퍼_초과시_alert(self):
        # 20 runs 중 5 cold_start = 25% > 20%
        for i in range(20):
            emit_product_identity_run(
                tool_calls_total=1, reanalyze_count=0, catalog_count=1, clarify_count=0,
                failure_mode=None, needs_user_input=False, confirmed_source="",
                cold_start=(i < 5),
            )
        status = compute_alert_status()
        assert status["status"] == "alert"
        assert any("cold_start_rate" in a for a in status["alerts"])

    def test_fallback_10퍼_초과시_alert(self):
        # 20 runs 중 3 fallback = 15% > 10%
        for i in range(20):
            emit_product_identity_run(
                tool_calls_total=0, reanalyze_count=0, catalog_count=0, clarify_count=0,
                failure_mode="react_exception" if i < 3 else None,
                needs_user_input=False, confirmed_source="",
            )
        status = compute_alert_status()
        assert status["status"] == "alert"
        assert any("fallback_rate" in a for a in status["alerts"])

    def test_정상_범위면_ok(self):
        # 20 runs 중 fallback 1 (5%), cold_start 1 (5%)
        for i in range(20):
            emit_product_identity_run(
                tool_calls_total=1, reanalyze_count=0, catalog_count=1, clarify_count=0,
                failure_mode="react_exception" if i == 0 else None,
                needs_user_input=False, confirmed_source="",
                cold_start=(i == 1),
            )
        status = compute_alert_status()
        assert status["status"] == "ok"
        assert status["alerts"] == []
