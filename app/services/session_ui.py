"""
세션 DB 레코드 → UI 응답 평탄화.

SessionService의 오케스트레이션 책임과 UI 응답 조립 책임을 분리.
외부에서는 이 모듈의 build_session_ui_response()만 import한다.
"""
from __future__ import annotations

from typing import Any

from app.domain.session_status import resolve_next_action


def build_session_ui_response(session: dict[str, Any]) -> dict[str, Any]:
    """DB 레코드 → UI 응답 평탄화. SessionService 외부에서도 재사용 가능."""
    product_data = session.get("product_data_jsonb") or {}
    listing_data = session.get("listing_data_jsonb") or {}
    workflow_meta = session.get("workflow_meta_jsonb") or {}
    status = session.get("status", "")
    needs_input = bool(product_data.get("needs_user_input", False))

    # 게시 결과를 프론트엔드 PlatformResult[] 형태로 변환
    raw_publish = workflow_meta.get("publish_results") or {}
    platform_results = []
    for platform, detail in raw_publish.items():
        if isinstance(detail, dict):
            entry: dict[str, Any] = {
                "platform": platform,
                "success": detail.get("success", False),
                "url": detail.get("external_url"),
                "error": detail.get("error_message"),
            }
            if detail.get("source"):
                entry["source"] = detail["source"]
            platform_results.append(entry)

    return {
        "session_id": session.get("id") or session.get("session_id"),
        "status": status,
        "checkpoint": workflow_meta.get("checkpoint"),
        "next_action": resolve_next_action(status, needs_input),
        "needs_user_input": needs_input,
        # 프론트엔드 계약: clarification_prompt
        "clarification_prompt": product_data.get("user_input_prompt"),
        "selected_platforms": session.get("selected_platforms_jsonb") or [],
        # 평탄화된 필드 (프론트엔드 SessionResponse 계약)
        "image_urls": product_data.get("image_paths") or [],
        "product_candidates": product_data.get("candidates") or [],
        "confirmed_product": product_data.get("confirmed_product"),
        "canonical_listing": listing_data.get("canonical_listing"),
        "market_context": listing_data.get("market_context"),
        "platform_results": platform_results,
        "optimization_suggestion": listing_data.get("optimization_suggestion"),
        "rewrite_instruction": listing_data.get("rewrite_instruction"),
        "last_error": workflow_meta.get("last_error"),
        # 중첩 필드 (하위 호환)
        "product": {
            "image_paths": product_data.get("image_paths") or [],
            "candidates": product_data.get("candidates") or [],
            "confirmed_product": product_data.get("confirmed_product"),
            "analysis_source": product_data.get("analysis_source"),
        },
        "listing": {
            "market_context": listing_data.get("market_context"),
            "strategy": listing_data.get("strategy"),
            "canonical_listing": listing_data.get("canonical_listing"),
            "platform_packages": listing_data.get("platform_packages") or {},
            "optimization_suggestion": listing_data.get("optimization_suggestion"),
        },
        "publish": {
            "results": raw_publish,
            "diagnostics": workflow_meta.get("publish_diagnostics") or [],
        },
        "agent_trace": {
            "tool_calls": workflow_meta.get("tool_calls") or [],
            "rewrite_history": workflow_meta.get("rewrite_history") or [],
            "decision_rationale": workflow_meta.get("decision_rationale") or [],
            "plan": workflow_meta.get("plan"),
            "critic_score": workflow_meta.get("critic_score"),
            "critic_feedback": workflow_meta.get("critic_feedback") or [],
        },
        "debug": {
            "last_error": workflow_meta.get("last_error"),
        },
    }
