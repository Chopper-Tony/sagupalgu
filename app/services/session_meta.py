"""
session_meta — workflow_meta 순수 함수 집합.

workflow_meta dict의 체크포인트·히스토리·결과 조작을 순수 함수로 제공.
SessionService는 이 모듈을 통해서만 workflow_meta를 변경한다.

모든 함수는 workflow_meta dict를 in-place로 수정하며 None을 반환한다.
"""
from __future__ import annotations

import datetime
from typing import Any, Dict, List


def append_tool_calls(workflow_meta: Dict, new_calls: List[Dict]) -> None:
    """tool_calls 리스트에 새 항목을 병합한다."""
    workflow_meta["tool_calls"] = (workflow_meta.get("tool_calls") or []) + new_calls


def set_analysis_checkpoint(workflow_meta: Dict, needs_input: bool) -> None:
    """상품 분석 결과에 따라 A 단계 체크포인트를 설정한다."""
    workflow_meta["checkpoint"] = "A_needs_user_input" if needs_input else "A_before_confirm"


def set_product_confirmed(workflow_meta: Dict) -> None:
    """상품 확정 후 A 단계 완료 체크포인트를 설정한다."""
    workflow_meta["checkpoint"] = "A_complete"


def normalize_listing_meta(workflow_meta: Dict, new_tool_calls: List[Dict]) -> None:
    """판매글 생성(재생성) 시 C 단계 체크포인트를 B로 되돌리고 잔여 게시 결과를 제거한다."""
    if workflow_meta.get("checkpoint") in {"C_prepared", "C_complete"}:
        workflow_meta["checkpoint"] = "B_complete"
    workflow_meta.pop("publish_results", None)
    append_tool_calls(workflow_meta, new_tool_calls)


def append_rewrite_entry(
    workflow_meta: Dict, instruction: str, new_tool_calls: List[Dict]
) -> None:
    """재작성 히스토리에 항목을 추가하고 tool_calls를 병합한다."""
    rewrite_history = workflow_meta.get("rewrite_history") or []
    rewrite_history.append({
        "instruction": instruction,
        "timestamp": datetime.datetime.utcnow().isoformat(),
    })
    workflow_meta["rewrite_history"] = rewrite_history
    append_tool_calls(workflow_meta, new_tool_calls)


def set_publish_prepared(workflow_meta: Dict) -> None:
    """게시 준비 완료 체크포인트를 설정하고 이전 게시 결과를 제거한다."""
    workflow_meta["checkpoint"] = "C_prepared"
    workflow_meta.pop("publish_results", None)


def set_publish_complete(workflow_meta: Dict, publish_results: Any) -> None:
    """게시 완료 체크포인트와 결과를 저장한다."""
    workflow_meta["checkpoint"] = "C_complete"
    workflow_meta["publish_results"] = publish_results


def set_publish_diagnostics(
    workflow_meta: Dict, diagnostics: Any, tool_calls: List[Dict]
) -> None:
    """게시 실패 진단 결과를 저장하고 recovery tool_calls를 병합한다."""
    workflow_meta["publish_diagnostics"] = diagnostics
    append_tool_calls(workflow_meta, tool_calls)


def set_sale_status(workflow_meta: Dict, sale_status: str) -> None:
    """판매 상태를 workflow_meta에 기록한다."""
    workflow_meta["sale_status"] = sale_status
