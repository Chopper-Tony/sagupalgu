"""
경량 in-process metric 카운터 + 구조화 emission.

PR4-3: product_identity Tool Agent 의 cold_start / fallback / reanalyze /
catalog hit / clarify 비율을 누적해 운영 알람 임계 (cold_start > 20%,
fallback > 10%) 판단용 데이터 제공.

설계 원칙:
- 외부 metric backend (Prometheus/StatsD) 의존 0. 운영 진입 후 별도 PR 에서 export.
- thread-safe (lock 사용). FastAPI worker 1 process 가정이지만 향후 worker 분리 대비.
- 누적 카운터만 제공. histogram/quantile 은 backend 도입 시 추가.
- snapshot() 으로 운영 진단 엔드포인트가 read-only 으로 가져갈 수 있게.
"""
from __future__ import annotations

import logging
import threading
from collections import Counter
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


# ── 구조화 이벤트 이름 ──────────────────────────────────────────────────
PRODUCT_IDENTITY_RUN = "product_identity.run"
PRODUCT_IDENTITY_FALLBACK = "product_identity.fallback"
PRODUCT_IDENTITY_COLD_START = "product_identity.cold_start"
PRODUCT_IDENTITY_TOOL_CALL = "product_identity.tool_call"


class _MetricRegistry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counters: Counter[str] = Counter()
        self._labeled: Dict[str, Counter[str]] = {}

    def incr(self, name: str, value: int = 1) -> None:
        with self._lock:
            self._counters[name] += value

    def incr_labeled(self, name: str, label: str, value: int = 1) -> None:
        with self._lock:
            bucket = self._labeled.setdefault(name, Counter())
            bucket[label] += value

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "counters": dict(self._counters),
                "labeled": {k: dict(v) for k, v in self._labeled.items()},
            }

    def reset(self) -> None:
        """테스트 격리용. 운영에서는 호출 금지."""
        with self._lock:
            self._counters.clear()
            self._labeled.clear()


_registry = _MetricRegistry()


def get_registry() -> _MetricRegistry:
    return _registry


# ── product_identity 전용 emit helper ───────────────────────────────────


def emit_product_identity_run(
    *,
    tool_calls_total: int,
    reanalyze_count: int,
    catalog_count: int,
    clarify_count: int,
    failure_mode: Optional[str],
    needs_user_input: bool,
    confirmed_source: str,
    cold_start: bool = False,
) -> None:
    """product_identity_agent 1회 실행 결과를 metric 으로 누적.

    cold_start: catalog 결과가 cold_start 였는지 (lc_rag_product_catalog_tool 응답 기반).
                현재는 호출측이 명시적으로 전달. 자동 추론은 PR4-3 후속 (tool 결과 캡처 필요).

    LLM 호출 없는 fallback 경로도 호출해야 비율 계산이 정확해진다.
    """
    _registry.incr(f"{PRODUCT_IDENTITY_RUN}.total")

    if failure_mode:
        _registry.incr(f"{PRODUCT_IDENTITY_FALLBACK}.total")
        _registry.incr_labeled(PRODUCT_IDENTITY_FALLBACK, failure_mode)

    if cold_start:
        _registry.incr(f"{PRODUCT_IDENTITY_COLD_START}.total")

    if reanalyze_count:
        _registry.incr_labeled(PRODUCT_IDENTITY_TOOL_CALL, "reanalyze", reanalyze_count)
    if catalog_count:
        _registry.incr_labeled(PRODUCT_IDENTITY_TOOL_CALL, "catalog", catalog_count)
    if clarify_count:
        _registry.incr_labeled(PRODUCT_IDENTITY_TOOL_CALL, "clarify", clarify_count)

    structured = {
        "event": PRODUCT_IDENTITY_RUN,
        "tool_calls_total": tool_calls_total,
        "reanalyze_count": reanalyze_count,
        "catalog_count": catalog_count,
        "clarify_count": clarify_count,
        "failure_mode": failure_mode,
        "needs_user_input": needs_user_input,
        "confirmed_source": confirmed_source,
        "cold_start": cold_start,
    }
    logger.info(f"[metric] {structured}")


# ── 알람 임계 (CTO PR4 plan: cold_start > 20%, fallback > 10%) ───────


COLD_START_ALERT_THRESHOLD = 0.20
FALLBACK_ALERT_THRESHOLD = 0.10
ALERT_MIN_RUN_COUNT = 20  # 통계적 의미 최소 표본


def compute_alert_status() -> Dict[str, Any]:
    """현재 누적 카운터로 알람 임계 도달 여부 판정. snapshot 엔드포인트용."""
    snap = _registry.snapshot()
    counters = snap["counters"]
    runs = counters.get(f"{PRODUCT_IDENTITY_RUN}.total", 0)
    if runs < ALERT_MIN_RUN_COUNT:
        return {
            "status": "insufficient_data",
            "runs": runs,
            "min_runs": ALERT_MIN_RUN_COUNT,
        }

    cold_starts = counters.get(f"{PRODUCT_IDENTITY_COLD_START}.total", 0)
    fallbacks = counters.get(f"{PRODUCT_IDENTITY_FALLBACK}.total", 0)
    cold_rate = cold_starts / runs
    fallback_rate = fallbacks / runs

    alerts = []
    if cold_rate > COLD_START_ALERT_THRESHOLD:
        alerts.append(f"cold_start_rate={cold_rate:.1%} > {COLD_START_ALERT_THRESHOLD:.0%}")
    if fallback_rate > FALLBACK_ALERT_THRESHOLD:
        alerts.append(f"fallback_rate={fallback_rate:.1%} > {FALLBACK_ALERT_THRESHOLD:.0%}")

    return {
        "status": "alert" if alerts else "ok",
        "runs": runs,
        "cold_start_rate": round(cold_rate, 4),
        "fallback_rate": round(fallback_rate, 4),
        "alerts": alerts,
    }
