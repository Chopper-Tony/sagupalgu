"""
Goal 기반 전략 상수 및 순수 함수.

mission_goal(fast_sell / balanced / profit_max)에 따라
pricing · copywriting · critic 행동이 달라지도록 하는 단일 진실 원천.
"""
from __future__ import annotations

from typing import Any, Dict

# ── 가격 배수 ────────────────────────────────────────────────────

PRICING_MULTIPLIER: Dict[str, Dict[str, float]] = {
    "fast_sell":  {"high_sample": 0.90, "low_sample": 0.88},
    "balanced":   {"high_sample": 0.97, "low_sample": 0.95},
    "profit_max": {"high_sample": 1.05, "low_sample": 1.02},
}

# ── 카피라이팅 톤 ────────────────────────────────────────────────

COPYWRITING_TONE: Dict[str, str] = {
    "fast_sell": (
        "간결하고 긴급감 있는 문구. "
        "'빠른 거래 원합니다', '오늘 가격' 등 즉시 판매 유도 표현 사용. "
        "설명은 핵심만 짧게."
    ),
    "balanced": (
        "실용적이고 신뢰감 있는 문구. "
        "상태·구성품 명확 기술. 합리적 톤 유지."
    ),
    "profit_max": (
        "프리미엄 느낌의 고급 문구. "
        "'깨끗하게 관리', '풀박스', '정품' 등 가치를 강조. "
        "상세 스펙과 차별점 부각."
    ),
}

# ── 네고 정책 ────────────────────────────────────────────────────

NEGOTIATION_POLICY: Dict[str, str] = {
    "fast_sell":  "negotiation welcome, fast deal priority",
    "balanced":   "small negotiation allowed",
    "profit_max": "firm price, value justified",
}

# ── Critic 평가 기준 ─────────────────────────────────────────────

CRITIC_CRITERIA: Dict[str, Dict[str, Any]] = {
    "fast_sell":  {"price_threshold": 1.4, "min_desc_len": 30, "trust_penalty": 5},
    "balanced":   {"price_threshold": 1.3, "min_desc_len": 50, "trust_penalty": 10},
    "profit_max": {"price_threshold": 1.5, "min_desc_len": 80, "trust_penalty": 15},
}

_DEFAULT_GOAL = "balanced"


# ── 순수 함수 ────────────────────────────────────────────────────


def get_pricing_multiplier(goal: str, sample_count: int) -> float:
    """goal과 sample_count에 따른 가격 배수를 반환한다."""
    entry = PRICING_MULTIPLIER.get(goal, PRICING_MULTIPLIER[_DEFAULT_GOAL])
    if sample_count >= 3:
        return entry["high_sample"]
    return entry["low_sample"]


def get_copywriting_tone(goal: str) -> str:
    """goal에 따른 카피라이팅 톤 지시를 반환한다."""
    return COPYWRITING_TONE.get(goal, COPYWRITING_TONE[_DEFAULT_GOAL])


def get_negotiation_policy(goal: str) -> str:
    """goal에 따른 네고 정책을 반환한다."""
    return NEGOTIATION_POLICY.get(goal, NEGOTIATION_POLICY[_DEFAULT_GOAL])


def get_critic_criteria(goal: str) -> Dict[str, Any]:
    """goal에 따른 critic 평가 기준을 반환한다."""
    return CRITIC_CRITERIA.get(goal, CRITIC_CRITERIA[_DEFAULT_GOAL])
