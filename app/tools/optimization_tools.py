"""
Agent 5 툴 — 판매 후 가격 최적화
"""
from __future__ import annotations

import logging
from typing import Any, Dict

from app.tools._common import make_tool_call

logger = logging.getLogger(__name__)


async def price_optimization_tool(
    canonical_listing: Dict[str, Any],
    confirmed_product: Dict[str, Any],
    sale_status: str,
    days_listed: int = 7,
) -> Dict[str, Any]:
    """미판매 시 가격 재전략 제안. 판매 후 최적화 에이전트가 호출."""
    tool_input = {
        "sale_status": sale_status,
        "days_listed": days_listed,
        "current_price": canonical_listing.get("price", 0),
    }
    try:
        current_price = int(canonical_listing.get("price", 0) or 0)
        if sale_status != "unsold" or current_price <= 0:
            return make_tool_call("price_optimization_tool", tool_input, {"suggestion": None}, success=True)

        if days_listed >= 21:
            drop_rate, urgency = 0.15, "critical"
        elif days_listed >= 14:
            drop_rate, urgency = 0.10, "high"
        else:
            drop_rate, urgency = 0.05, "medium"

        suggested_price = int(current_price * (1 - drop_rate) // 1000 * 1000)

        # 기본 제안: 가격 인하
        suggestions = [
            f"가격을 {current_price:,}원 → {suggested_price:,}원으로 인하 ({int(drop_rate*100)}% 할인)",
        ]

        # 14일 이상: 제목 변경 제안
        if days_listed >= 14:
            suggestions.append("제목에 '급처', '가격인하' 키워드를 추가하여 관심을 유도하세요")

        # 21일 이상: 재게시 + 사진 변경 제안
        if days_listed >= 21:
            suggestions.append("게시글을 삭제 후 새로 올려 노출 순위를 높이세요")
            suggestions.append("대표 사진을 다른 각도로 교체하면 클릭률이 올라갑니다")

        output = {
            "type": "price_drop",
            "current_price": current_price,
            "suggested_price": suggested_price,
            "reason": f"{days_listed}일간 미판매 — {int(drop_rate*100)}% 인하 제안",
            "suggestions": suggestions,
            "urgency": urgency,
            "recommend_relist": days_listed >= 21,
        }
        return make_tool_call("price_optimization_tool", tool_input, output, success=True)

    except Exception as e:
        return make_tool_call("price_optimization_tool", tool_input, {"suggestion": None}, success=False, error=str(e))
