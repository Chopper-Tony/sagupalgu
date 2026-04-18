"""
경량 in-process metric 카운터 + 구조화 emission + export hook.

PR4-3: product_identity Tool Agent 의 cold_start / fallback / reanalyze /
catalog hit / clarify 비율을 누적해 운영 알람 임계 (cold_start > 20%,
fallback > 10%) 판단용 데이터 제공.

⚠️ 임시 레이어 (CTO PR4-3 #1):
  현재 in-process counter 는 프로세스 재시작 시 데이터 유실 + 분산 환경 aggregation
  불가. 운영 안정화 후 별도 PR 에서 Prometheus / OpenTelemetry / structured log 수집기로
  교체 예정. 이 모듈의 외부 인터페이스 (emit_*, get_registry, register_exporter,
  compute_alert_status) 는 유지하되 내부는 위 export 백엔드로 위임하게 된다.

설계 원칙:
- 외부 metric backend (Prometheus/StatsD) 의존 0. 운영 진입 후 교체.
- thread-safe (lock 사용). FastAPI worker 1 process 가정이지만 향후 worker 분리 대비.
- 누적 카운터만 제공. histogram/quantile 은 backend 도입 시 추가.
- snapshot() 으로 운영 진단 엔드포인트가 read-only 으로 가져갈 수 있게.
- register_exporter() 로 emit 시점에 외부 sink (log / Prometheus / Webhook) 로 push.
"""
from __future__ import annotations

import logging
import threading
from collections import Counter
from typing import Any, Callable, Dict, List, Optional

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


# ── Export hook (CTO PR4-3 #1) ──────────────────────────────────────────
# emit 시점에 호출되는 callback 등록. structured log exporter 가 기본으로 등록됨.
# 운영 진입 후 Prometheus / OTel exporter 를 register 만 하면 코드 변경 없이 push 시작.

ExporterFn = Callable[[Dict[str, Any]], None]
_exporters: List[ExporterFn] = []
_exporters_lock = threading.Lock()


def register_exporter(fn: ExporterFn) -> None:
    """외부 metric sink 등록. emit 마다 동기 호출 (실패는 internal log 로 swallow).
    동일 exporter 중복 등록 금지 — 호출측이 보장.
    """
    with _exporters_lock:
        _exporters.append(fn)


def clear_exporters() -> None:
    """테스트 격리용."""
    with _exporters_lock:
        _exporters.clear()


def _structured_log_exporter(event: Dict[str, Any]) -> None:
    """기본 exporter — structured log 로 emit. 외부 log aggregator (ELK/Loki) 가
    수집해 dashboard 화 가능."""
    logger.info(f"[metric] {event}")


# 모듈 로드 시점에 기본 exporter 1개 등록
register_exporter(_structured_log_exporter)


def _dispatch_to_exporters(event: Dict[str, Any]) -> None:
    with _exporters_lock:
        targets = list(_exporters)
    for fn in targets:
        try:
            fn(event)
        except Exception as e:  # exporter 장애가 본 흐름 막지 않게
            logger.warning(f"[metric] exporter failed: {e}")


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
    """product_identity_agent 1회 실행 결과를 metric 으로 누적 + exporter dispatch.

    cold_start: catalog 결과가 cold_start 였는지 (lc_rag_product_catalog_tool 응답 기반).
                현재는 호출측이 명시적으로 전달.

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
    _dispatch_to_exporters(structured)


# ── 알람 임계 (CTO PR4 plan: cold_start > 20%, fallback > 10%) ───────


COLD_START_ALERT_THRESHOLD = 0.20
FALLBACK_ALERT_THRESHOLD = 0.10
ALERT_MIN_RUN_COUNT = 20  # 통계적 의미 최소 표본


def compute_alert_status() -> Dict[str, Any]:
    """현재 누적 카운터로 알람 임계 도달 여부 판정. snapshot 엔드포인트용.

    ⚠️ 임계는 static 값 (CTO PR4-3 #2). 운영 진입 후 baseline 3~7일 수집 → 실제
    분포로 재조정. 자세한 튜닝 절차는 .claude/rules/architecture.md 의
    'Product Identity 운영 runbook' 참조.
    """
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


def compute_diagnostic_breakdown() -> Dict[str, Any]:
    """CTO PR4-3 #4: '왜 fallback 이 늘었는가' 원인 추적용.

    - tool_call 별 호출 수 (reanalyze / catalog / clarify)
    - failure_mode 별 fallback 수 (react_exception / parse_error / contract_violation /
      total_budget_exceeded / clarify_forced_by_heuristic 등)

    Returns: {tool_calls: {label: count}, failure_modes: {label: count}, total_runs: int}
    """
    snap = _registry.snapshot()
    return {
        "total_runs": snap["counters"].get(f"{PRODUCT_IDENTITY_RUN}.total", 0),
        "tool_calls": dict(snap["labeled"].get(PRODUCT_IDENTITY_TOOL_CALL, {})),
        "failure_modes": dict(snap["labeled"].get(PRODUCT_IDENTITY_FALLBACK, {})),
    }
