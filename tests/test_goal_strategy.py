"""goal_strategy 순수 함수 unit 테스트."""
import pytest

from app.domain.goal_strategy import (
    COPYWRITING_TONE,
    CRITIC_CRITERIA,
    NEGOTIATION_POLICY,
    PRICING_MULTIPLIER,
    get_copywriting_tone,
    get_critic_criteria,
    get_negotiation_policy,
    get_pricing_multiplier,
)

# ── pricing multiplier ──────────────────────────────────────────


class TestGetPricingMultiplier:
    @pytest.mark.unit
    @pytest.mark.parametrize("goal,sample,expected", [
        ("fast_sell", 5, 0.90),
        ("fast_sell", 1, 0.88),
        ("balanced", 3, 0.97),
        ("balanced", 2, 0.95),
        ("profit_max", 10, 1.05),
        ("profit_max", 0, 1.02),
    ])
    def test_known_goals(self, goal, sample, expected):
        assert get_pricing_multiplier(goal, sample) == expected

    @pytest.mark.unit
    def test_unknown_goal_falls_back_to_balanced_high(self):
        assert get_pricing_multiplier("unknown", 5) == 0.97

    @pytest.mark.unit
    def test_unknown_goal_falls_back_to_balanced_low(self):
        assert get_pricing_multiplier("unknown", 1) == 0.95

    @pytest.mark.unit
    def test_boundary_sample_count_3(self):
        """sample_count == 3은 high_sample 사용."""
        assert get_pricing_multiplier("balanced", 3) == 0.97


# ── copywriting tone ────────────────────────────────────────────


class TestGetCopywritingTone:
    @pytest.mark.unit
    @pytest.mark.parametrize("goal", ["fast_sell", "balanced", "profit_max"])
    def test_known_goals(self, goal):
        tone = get_copywriting_tone(goal)
        assert isinstance(tone, str)
        assert len(tone) > 10
        assert tone == COPYWRITING_TONE[goal]

    @pytest.mark.unit
    def test_unknown_goal_falls_back_to_balanced(self):
        assert get_copywriting_tone("xyz") == COPYWRITING_TONE["balanced"]


# ── negotiation policy ──────────────────────────────────────────


class TestGetNegotiationPolicy:
    @pytest.mark.unit
    @pytest.mark.parametrize("goal,expected", [
        ("fast_sell", "negotiation welcome, fast deal priority"),
        ("balanced", "small negotiation allowed"),
        ("profit_max", "firm price, value justified"),
    ])
    def test_known_goals(self, goal, expected):
        assert get_negotiation_policy(goal) == expected

    @pytest.mark.unit
    def test_unknown_goal_falls_back_to_balanced(self):
        assert get_negotiation_policy("nope") == NEGOTIATION_POLICY["balanced"]


# ── critic criteria ─────────────────────────────────────────────


class TestGetCriticCriteria:
    @pytest.mark.unit
    @pytest.mark.parametrize("goal", ["fast_sell", "balanced", "profit_max"])
    def test_known_goals_have_required_keys(self, goal):
        c = get_critic_criteria(goal)
        assert "price_threshold" in c
        assert "min_desc_len" in c
        assert "trust_penalty" in c

    @pytest.mark.unit
    def test_fast_sell_is_most_lenient_on_description(self):
        assert get_critic_criteria("fast_sell")["min_desc_len"] < get_critic_criteria("balanced")["min_desc_len"]

    @pytest.mark.unit
    def test_profit_max_requires_longest_description(self):
        assert get_critic_criteria("profit_max")["min_desc_len"] > get_critic_criteria("balanced")["min_desc_len"]

    @pytest.mark.unit
    def test_unknown_goal_falls_back_to_balanced(self):
        assert get_critic_criteria("???") == CRITIC_CRITERIA["balanced"]


# ── 맵 완전성 ───────────────────────────────────────────────────


class TestMapCompleteness:
    GOALS = {"fast_sell", "balanced", "profit_max"}

    @pytest.mark.unit
    def test_pricing_multiplier_covers_all_goals(self):
        assert set(PRICING_MULTIPLIER.keys()) == self.GOALS

    @pytest.mark.unit
    def test_copywriting_tone_covers_all_goals(self):
        assert set(COPYWRITING_TONE.keys()) == self.GOALS

    @pytest.mark.unit
    def test_negotiation_policy_covers_all_goals(self):
        assert set(NEGOTIATION_POLICY.keys()) == self.GOALS

    @pytest.mark.unit
    def test_critic_criteria_covers_all_goals(self):
        assert set(CRITIC_CRITERIA.keys()) == self.GOALS
