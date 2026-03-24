"""
session_meta 순수 함수 unit 테스트

외부 의존성 없음. workflow_meta dict 조작 함수 9개를 전부 검증한다.
"""
import pytest

from app.services.session_meta import (
    append_rewrite_entry,
    append_tool_calls,
    normalize_listing_meta,
    set_analysis_checkpoint,
    set_product_confirmed,
    set_publish_complete,
    set_publish_diagnostics,
    set_publish_prepared,
    set_sale_status,
)


# ─────────────────────────────────────────────────────────────────
# append_tool_calls
# ─────────────────────────────────────────────────────────────────

class TestAppendToolCalls:

    @pytest.mark.unit
    def test_appends_to_empty(self):
        meta = {}
        append_tool_calls(meta, [{"tool_name": "foo"}])
        assert meta["tool_calls"] == [{"tool_name": "foo"}]

    @pytest.mark.unit
    def test_appends_to_existing(self):
        meta = {"tool_calls": [{"tool_name": "a"}]}
        append_tool_calls(meta, [{"tool_name": "b"}])
        assert meta["tool_calls"] == [{"tool_name": "a"}, {"tool_name": "b"}]

    @pytest.mark.unit
    def test_empty_new_calls_no_change(self):
        meta = {"tool_calls": [{"tool_name": "a"}]}
        append_tool_calls(meta, [])
        assert meta["tool_calls"] == [{"tool_name": "a"}]

    @pytest.mark.unit
    def test_none_existing_treated_as_empty(self):
        meta = {"tool_calls": None}
        append_tool_calls(meta, [{"tool_name": "x"}])
        assert meta["tool_calls"] == [{"tool_name": "x"}]


# ─────────────────────────────────────────────────────────────────
# set_analysis_checkpoint
# ─────────────────────────────────────────────────────────────────

class TestSetAnalysisCheckpoint:

    @pytest.mark.unit
    def test_needs_input_true(self):
        meta = {}
        set_analysis_checkpoint(meta, needs_input=True)
        assert meta["checkpoint"] == "A_needs_user_input"

    @pytest.mark.unit
    def test_needs_input_false(self):
        meta = {}
        set_analysis_checkpoint(meta, needs_input=False)
        assert meta["checkpoint"] == "A_before_confirm"

    @pytest.mark.unit
    def test_overwrites_existing_checkpoint(self):
        meta = {"checkpoint": "old_value"}
        set_analysis_checkpoint(meta, needs_input=False)
        assert meta["checkpoint"] == "A_before_confirm"


# ─────────────────────────────────────────────────────────────────
# set_product_confirmed
# ─────────────────────────────────────────────────────────────────

class TestSetProductConfirmed:

    @pytest.mark.unit
    def test_sets_a_complete(self):
        meta = {}
        set_product_confirmed(meta)
        assert meta["checkpoint"] == "A_complete"

    @pytest.mark.unit
    def test_overwrites_any_previous(self):
        meta = {"checkpoint": "A_needs_user_input"}
        set_product_confirmed(meta)
        assert meta["checkpoint"] == "A_complete"


# ─────────────────────────────────────────────────────────────────
# normalize_listing_meta
# ─────────────────────────────────────────────────────────────────

class TestNormalizeListingMeta:

    @pytest.mark.unit
    def test_c_prepared_rolls_back_to_b_complete(self):
        meta = {"checkpoint": "C_prepared"}
        normalize_listing_meta(meta, [])
        assert meta["checkpoint"] == "B_complete"

    @pytest.mark.unit
    def test_c_complete_rolls_back_to_b_complete(self):
        meta = {"checkpoint": "C_complete"}
        normalize_listing_meta(meta, [])
        assert meta["checkpoint"] == "B_complete"

    @pytest.mark.unit
    def test_other_checkpoint_unchanged(self):
        meta = {"checkpoint": "B_complete"}
        normalize_listing_meta(meta, [])
        assert meta["checkpoint"] == "B_complete"

    @pytest.mark.unit
    def test_removes_publish_results(self):
        meta = {"checkpoint": "B_complete", "publish_results": {"bunjang": True}}
        normalize_listing_meta(meta, [])
        assert "publish_results" not in meta

    @pytest.mark.unit
    def test_merges_tool_calls(self):
        meta = {"tool_calls": [{"tool_name": "prev"}]}
        normalize_listing_meta(meta, [{"tool_name": "new"}])
        assert meta["tool_calls"] == [{"tool_name": "prev"}, {"tool_name": "new"}]


# ─────────────────────────────────────────────────────────────────
# append_rewrite_entry
# ─────────────────────────────────────────────────────────────────

class TestAppendRewriteEntry:

    @pytest.mark.unit
    def test_adds_instruction_to_history(self):
        meta = {}
        append_rewrite_entry(meta, "더 짧게", [])
        history = meta["rewrite_history"]
        assert len(history) == 1
        assert history[0]["instruction"] == "더 짧게"

    @pytest.mark.unit
    def test_timestamp_present(self):
        meta = {}
        append_rewrite_entry(meta, "instruction", [])
        assert "timestamp" in meta["rewrite_history"][0]

    @pytest.mark.unit
    def test_accumulates_multiple_entries(self):
        meta = {}
        append_rewrite_entry(meta, "first", [])
        append_rewrite_entry(meta, "second", [])
        assert len(meta["rewrite_history"]) == 2
        assert meta["rewrite_history"][1]["instruction"] == "second"

    @pytest.mark.unit
    def test_merges_tool_calls(self):
        meta = {}
        append_rewrite_entry(meta, "instruction", [{"tool_name": "rewrite"}])
        assert meta["tool_calls"] == [{"tool_name": "rewrite"}]


# ─────────────────────────────────────────────────────────────────
# set_publish_prepared
# ─────────────────────────────────────────────────────────────────

class TestSetPublishPrepared:

    @pytest.mark.unit
    def test_sets_c_prepared(self):
        meta = {}
        set_publish_prepared(meta)
        assert meta["checkpoint"] == "C_prepared"

    @pytest.mark.unit
    def test_removes_stale_publish_results(self):
        meta = {"publish_results": {"bunjang": True}}
        set_publish_prepared(meta)
        assert "publish_results" not in meta


# ─────────────────────────────────────────────────────────────────
# set_publish_complete
# ─────────────────────────────────────────────────────────────────

class TestSetPublishComplete:

    @pytest.mark.unit
    def test_sets_c_complete(self):
        meta = {}
        set_publish_complete(meta, {})
        assert meta["checkpoint"] == "C_complete"

    @pytest.mark.unit
    def test_stores_publish_results(self):
        results = {"bunjang": {"success": True, "url": "https://bunjang.kr/123"}}
        meta = {}
        set_publish_complete(meta, results)
        assert meta["publish_results"] == results


# ─────────────────────────────────────────────────────────────────
# set_publish_diagnostics
# ─────────────────────────────────────────────────────────────────

class TestSetPublishDiagnostics:

    @pytest.mark.unit
    def test_stores_diagnostics(self):
        meta = {}
        set_publish_diagnostics(meta, [{"platform": "bunjang", "issue": "login"}], [])
        assert meta["publish_diagnostics"] == [{"platform": "bunjang", "issue": "login"}]

    @pytest.mark.unit
    def test_merges_recovery_tool_calls(self):
        meta = {}
        set_publish_diagnostics(meta, [], [{"tool_name": "discord_alert"}])
        assert meta["tool_calls"] == [{"tool_name": "discord_alert"}]


# ─────────────────────────────────────────────────────────────────
# set_sale_status
# ─────────────────────────────────────────────────────────────────

class TestSetSaleStatus:

    @pytest.mark.unit
    def test_sets_sold(self):
        meta = {}
        set_sale_status(meta, "sold")
        assert meta["sale_status"] == "sold"

    @pytest.mark.unit
    def test_sets_unsold(self):
        meta = {}
        set_sale_status(meta, "unsold")
        assert meta["sale_status"] == "unsold"

    @pytest.mark.unit
    def test_overwrites_previous(self):
        meta = {"sale_status": "in_progress"}
        set_sale_status(meta, "sold")
        assert meta["sale_status"] == "sold"
