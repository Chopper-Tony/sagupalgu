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
    clear_exporters,
    compute_alert_status,
    compute_diagnostic_breakdown,
    emit_product_identity_run,
    get_registry,
    register_exporter,
    _structured_log_exporter,
)

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _reset_registry():
    get_registry().reset()
    # exporter 도 격리 — 기본 structured log 만 재등록
    clear_exporters()
    register_exporter(_structured_log_exporter)
    yield
    get_registry().reset()
    clear_exporters()
    register_exporter(_structured_log_exporter)


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


class TestExporterHook:
    """CTO PR4-3 #1: emit 시점에 등록된 exporter 들로 dispatch."""

    def test_등록된_exporter가_호출됨(self):
        captured = []
        register_exporter(lambda evt: captured.append(evt))

        emit_product_identity_run(
            tool_calls_total=2, reanalyze_count=1, catalog_count=1, clarify_count=0,
            failure_mode=None, needs_user_input=False, confirmed_source="catalog",
            cold_start=True,
        )
        # 기본 + 추가 = 2개. 추가한 게 캡처돼야.
        assert len(captured) == 1
        evt = captured[0]
        assert evt["event"] == PRODUCT_IDENTITY_RUN
        assert evt["tool_calls_total"] == 2
        assert evt["cold_start"] is True

    def test_exporter_예외가_emit_막지_않음(self):
        def broken(evt):
            raise RuntimeError("boom")

        register_exporter(broken)
        # 예외 발생해도 카운터 누적은 되어야 함
        emit_product_identity_run(
            tool_calls_total=0, reanalyze_count=0, catalog_count=0, clarify_count=0,
            failure_mode=None, needs_user_input=False, confirmed_source="",
        )
        snap = get_registry().snapshot()
        assert snap["counters"][f"{PRODUCT_IDENTITY_RUN}.total"] == 1


class TestDiagnosticBreakdown:
    """CTO PR4-3 #4: '왜 fallback 늘었는가' 원인 추적용 분해 helper."""

    def test_failure_mode_분포_확인(self):
        for mode in ["react_exception", "react_exception", "parse_error",
                     "react_total_budget_exceeded"]:
            emit_product_identity_run(
                tool_calls_total=0, reanalyze_count=0, catalog_count=0, clarify_count=0,
                failure_mode=mode, needs_user_input=False, confirmed_source="",
            )
        bd = compute_diagnostic_breakdown()
        assert bd["total_runs"] == 4
        assert bd["failure_modes"]["react_exception"] == 2
        assert bd["failure_modes"]["parse_error"] == 1
        assert bd["failure_modes"]["react_total_budget_exceeded"] == 1

    def test_tool_call_분포_확인(self):
        emit_product_identity_run(
            tool_calls_total=4, reanalyze_count=2, catalog_count=1, clarify_count=1,
            failure_mode=None, needs_user_input=True, confirmed_source="",
        )
        bd = compute_diagnostic_breakdown()
        assert bd["tool_calls"]["reanalyze"] == 2
        assert bd["tool_calls"]["catalog"] == 1
        assert bd["tool_calls"]["clarify"] == 1


class TestCatalogToolContract:
    """CTO PR4-3 #3: catalog tool 응답 스키마 검증 helper."""

    def test_정상_응답_통과(self):
        from app.tools.product_identity_tools import validate_catalog_tool_response

        ok = {
            "matches": [], "top_match_confidence": 0.0, "source_count": 0,
            "cold_start": True, "source_breakdown": {},
        }
        assert validate_catalog_tool_response(ok) is True

    def test_cold_start_누락시_실패(self):
        from app.tools.product_identity_tools import validate_catalog_tool_response

        bad = {"matches": [], "top_match_confidence": 0.5}
        assert validate_catalog_tool_response(bad) is False

    def test_cold_start_타입_위반시_실패(self):
        from app.tools.product_identity_tools import validate_catalog_tool_response

        bad = {"cold_start": "true"}  # str 아님 bool 이어야
        assert validate_catalog_tool_response(bad) is False

    def test_dict_아니면_실패(self):
        from app.tools.product_identity_tools import validate_catalog_tool_response

        assert validate_catalog_tool_response("not a dict") is False  # type: ignore[arg-type]
        assert validate_catalog_tool_response(None) is False  # type: ignore[arg-type]
