from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.graph.seller_copilot_state import (
    SellerCopilotState,
    create_initial_state,
)


def _get_graph():
    """LangGraph 컴파일 그래프를 lazy 로드한다. 미설치 환경에서 import 단계 통과."""
    from app.graph.seller_copilot_graph import seller_copilot_graph
    return seller_copilot_graph


class SellerCopilotRunner:
    """
    LangGraph 실행 진입점.

    책임:
    - 초기 state 조립 (session_id, image_paths, 외부 주입값)
    - seller_copilot_graph.invoke 호출
    - 최종 state 반환

    그 외 서비스 호출, asyncio 브릿지, reflection 로직은 포함하지 않는다.
    """

    def build_initial_state(
        self,
        session_id: str,
        image_paths: List[str],
        selected_platforms: Optional[List[str]] = None,
        user_product_input: Optional[Dict[str, Any]] = None,
        product_candidates: Optional[List[Dict[str, Any]]] = None,
        market_context: Optional[Dict[str, Any]] = None,
        rewrite_instruction: Optional[str] = None,
    ) -> SellerCopilotState:
        state = create_initial_state(
            session_id=session_id,
            image_paths=image_paths,
            selected_platforms=selected_platforms,
            user_product_input=user_product_input,
        )

        if product_candidates:
            state["product_candidates"] = product_candidates

        if market_context:
            state["market_context"] = market_context

        if rewrite_instruction:
            state["rewrite_instruction"] = rewrite_instruction

        return state

    def run(
        self,
        session_id: str,
        image_paths: List[str],
        selected_platforms: Optional[List[str]] = None,
        user_product_input: Optional[Dict[str, Any]] = None,
        product_candidates: Optional[List[Dict[str, Any]]] = None,
        market_context: Optional[Dict[str, Any]] = None,
        rewrite_instruction: Optional[str] = None,
    ) -> SellerCopilotState:
        initial_state = self.build_initial_state(
            session_id=session_id,
            image_paths=image_paths,
            selected_platforms=selected_platforms,
            user_product_input=user_product_input,
            product_candidates=product_candidates,
            market_context=market_context,
            rewrite_instruction=rewrite_instruction,
        )

        return _get_graph().invoke(initial_state)


seller_copilot_runner = SellerCopilotRunner()
