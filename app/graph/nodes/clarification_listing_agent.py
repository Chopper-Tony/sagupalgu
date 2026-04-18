"""
DEPRECATED (PR3): pre_listing_clarification_node는 clarification_node.py로 통합됨.

분류 (Target Architecture, 4+2+5):
  → Single Tool Node (PR3 통합 후 alias만 유지)

PR3 변경:
  pre_listing_clarification_node() 호출은 clarification_node()로 위임된다.
  통합 entry point는 state로 모드 자동 분기 (product / pre_listing / no-op).

TODO(PR4-cleanup): graph builder가 새 clarification_node로 완전 전환되면
  이 파일과 LISTING_INFO_REQUIREMENTS·내부 함수들을 제거.
  현재는 외부 import 호환을 위해 alias + 기존 export만 유지.
"""
from __future__ import annotations

from app.graph.nodes.clarification_node import (
    _LISTING_INFO_REQUIREMENTS,
    _detect_missing_info,
    _gather_existing_info,
    _generate_questions_llm,
    _generate_questions_rule,
    clarification_node as _unified_clarification_node,
)
from app.graph.seller_copilot_state import SellerCopilotState


# 외부 import 호환 (PR2 이전 코드가 이 상수를 직접 참조했을 수 있음)
LISTING_INFO_REQUIREMENTS = list(_LISTING_INFO_REQUIREMENTS)


def pre_listing_clarification_node(state: SellerCopilotState) -> SellerCopilotState:
    """Deprecated alias (PR3): clarification_node로 위임.

    제거 시점: PR4 (graph builder가 신 노드로 전환된 뒤).
    """
    return _unified_clarification_node(state)
