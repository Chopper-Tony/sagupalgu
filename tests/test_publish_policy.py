"""publish_policy 순수 함수 + PublishService 신뢰성 테스트."""
import pytest

from app.domain.publish_policy import (
    DISCORD_ALERT_THRESHOLD,
    FAILURE_TAXONOMY,
    MAX_PUBLISH_RETRIES,
    PUBLISH_TIMEOUT_SECONDS,
    classify_error,
    get_retry_delay,
)


# ── classify_error ──────────────────────────────────────────────


class TestClassifyError:
    @pytest.mark.unit
    @pytest.mark.parametrize("code", list(FAILURE_TAXONOMY.keys()))
    def test_known_codes_return_matching_entry(self, code):
        result = classify_error(code)
        assert result["error_code"] == code
        assert "category" in result
        assert "auto_recoverable" in result

    @pytest.mark.unit
    def test_timeout_is_auto_recoverable(self):
        result = classify_error("timeout")
        assert result["auto_recoverable"] is True

    @pytest.mark.unit
    def test_login_expired_not_recoverable(self):
        result = classify_error("login_expired")
        assert result["auto_recoverable"] is False

    @pytest.mark.unit
    def test_unknown_code_falls_back_to_message_timeout(self):
        result = classify_error("xxx", "request timed out after 60s")
        assert result["error_code"] == "timeout"

    @pytest.mark.unit
    def test_unknown_code_falls_back_to_message_login(self):
        result = classify_error("xxx", "login session expired")
        assert result["error_code"] == "login_expired"

    @pytest.mark.unit
    def test_unknown_code_falls_back_to_message_network(self):
        result = classify_error("xxx", "connection refused")
        assert result["error_code"] == "network_error"

    @pytest.mark.unit
    def test_unknown_code_falls_back_to_message_policy(self):
        result = classify_error("xxx", "content policy violation")
        assert result["error_code"] == "content_policy"

    @pytest.mark.unit
    def test_unknown_code_falls_back_to_message_503(self):
        result = classify_error("xxx", "503 service unavailable")
        assert result["error_code"] == "platform_unavailable"

    @pytest.mark.unit
    def test_completely_unknown_returns_publish_exception(self):
        result = classify_error("xxx", "something weird happened")
        assert result["error_code"] == "publish_exception"
        assert result["auto_recoverable"] is False


# ── get_retry_delay ─────────────────────────────────────────────


class TestGetRetryDelay:
    @pytest.mark.unit
    def test_exponential_backoff(self):
        delays = [get_retry_delay(i) for i in range(3)]
        assert delays[0] == 5.0
        assert delays[1] == 10.0
        assert delays[2] == 20.0

    @pytest.mark.unit
    def test_first_attempt_is_base_delay(self):
        assert get_retry_delay(0) == 5.0


# ── 상수 검증 ───────────────────────────────────────────────────


class TestConstants:
    @pytest.mark.unit
    def test_timeout_is_positive(self):
        assert PUBLISH_TIMEOUT_SECONDS > 0

    @pytest.mark.unit
    def test_max_retries_is_reasonable(self):
        assert 1 <= MAX_PUBLISH_RETRIES <= 5

    @pytest.mark.unit
    def test_discord_alert_threshold_is_positive(self):
        assert DISCORD_ALERT_THRESHOLD >= 1

    @pytest.mark.unit
    def test_discord_alert_threshold_at_or_above_retries(self):
        """알림은 최소 재시도 횟수 이상이어야 의미가 있다."""
        assert DISCORD_ALERT_THRESHOLD >= MAX_PUBLISH_RETRIES

    @pytest.mark.unit
    def test_taxonomy_covers_essential_categories(self):
        categories = {v["category"] for v in FAILURE_TAXONOMY.values()}
        assert "network" in categories
        assert "auth" in categories
        assert "content" in categories


# ── taxonomy 완전성 ─────────────────────────────────────────────


class TestTaxonomyCompleteness:
    @pytest.mark.unit
    def test_all_entries_have_required_keys(self):
        for code, entry in FAILURE_TAXONOMY.items():
            assert "category" in entry, f"{code} missing category"
            assert "auto_recoverable" in entry, f"{code} missing auto_recoverable"
            assert "description" in entry, f"{code} missing description"
            assert isinstance(entry["auto_recoverable"], bool), f"{code} auto_recoverable not bool"

    @pytest.mark.unit
    def test_at_least_one_recoverable(self):
        recoverable = [c for c, e in FAILURE_TAXONOMY.items() if e["auto_recoverable"]]
        assert len(recoverable) >= 1
