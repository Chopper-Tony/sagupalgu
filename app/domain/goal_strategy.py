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

# ── 문의 응대 템플릿 (SC-3 코파일럿 fallback) ──────────────────

INQUIRY_REPLY_TEMPLATES: Dict[str, Dict[str, str]] = {
    "fast_sell": {
        "nego": "안녕하세요! 빠른 거래 원해서 {discount}원까지 가능합니다. 오늘 거래하실 수 있으면 바로 연락 주세요!",
        "condition": "안녕하세요! 사용감 거의 없고 상태 좋습니다. 사진 그대로이고, 빠른 거래 가능합니다!",
        "default": "안녕하세요! 관심 감사합니다. 빠른 거래 원하고 있어요. 궁금한 점 있으시면 편하게 물어봐 주세요!",
    },
    "balanced": {
        "nego": "안녕하세요! 현재 시세 대비 적정 가격으로 등록했어요. {discount}원 정도 조정 가능합니다. 직거래 가능하시면 택배비 절약돼요.",
        "condition": "안녕하세요! 상태 양호하고 구성품 모두 포함입니다. 추가 사진 필요하시면 보내드릴게요.",
        "default": "안녕하세요! 관심 감사합니다. 궁금한 점 있으시면 편하게 물어봐 주세요.",
    },
    "profit_max": {
        "nego": "안녕하세요! 깨끗하게 관리한 제품이라 표기 가격이 적정합니다. 가격 조정은 어렵지만 직거래 시 꼼꼼하게 확인하실 수 있어요.",
        "condition": "안녕하세요! 정품이고 사용감 거의 없이 관리했습니다. 풀박스 구성이에요. 사진 추가로 보내드릴까요?",
        "default": "안녕하세요! 관심 감사합니다. 프리미엄 상태의 제품이에요. 궁금하신 점 있으시면 말씀해 주세요.",
    },
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


def get_inquiry_reply_template(goal: str, inquiry_type: str, price: int = 0) -> str:
    """goal과 문의 유형에 따른 응답 템플릿을 반환한다.

    inquiry_type: "nego" | "condition" | "default"
    """
    templates = INQUIRY_REPLY_TEMPLATES.get(goal, INQUIRY_REPLY_TEMPLATES[_DEFAULT_GOAL])
    template = templates.get(inquiry_type, templates["default"])
    discount = int(price * 0.95) if price > 0 else 0
    return template.format(discount=f"{discount:,}")
