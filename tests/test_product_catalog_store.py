"""
PR4-1 Product Catalog 하이브리드 RAG store + sync service 테스트.

스코프:
  - 정규화 함수 (normalize_brand, normalize_model)
  - session → price_history 행 변환
  - hybrid_search_catalog의 cold_start 산출 + source_breakdown
  - sync_completed_sessions_to_price_history의 incremental cursor + 중복 skip

LLM/Supabase는 mock (CI 결정론).
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ── 정규화 unit ────────────────────────────────────────────────────────


class TestNormalize:
    @pytest.mark.unit
    def test_brand_alias_한글(self):
        from app.db.product_catalog_store import normalize_brand
        assert normalize_brand("애플") == "Apple"
        assert normalize_brand("삼성") == "Samsung"
        assert normalize_brand("샤오미") == "Xiaomi"

    @pytest.mark.unit
    def test_brand_alias_소문자_영문(self):
        from app.db.product_catalog_store import normalize_brand
        assert normalize_brand("apple") == "Apple"
        assert normalize_brand("samsung") == "Samsung"
        assert normalize_brand("LG") == "LG"

    @pytest.mark.unit
    def test_brand_alias_사전에_없으면_strip_원본(self):
        from app.db.product_catalog_store import normalize_brand
        assert normalize_brand("  Anker  ") == "Anker"
        assert normalize_brand("") == ""

    @pytest.mark.unit
    def test_model_공백_정규화(self):
        from app.db.product_catalog_store import normalize_model
        assert normalize_model("  iPhone   15  Pro  ") == "iPhone 15 Pro"
        assert normalize_model("") == ""


# ── Session → price_history row 변환 ──────────────────────────────────


class TestSessionToRow:
    @pytest.mark.unit
    def test_정상_변환(self):
        from app.db.product_catalog_store import session_to_price_history_row
        session = {
            "id": "session-1",
            "product_data_jsonb": {"confirmed_product": {"brand": "애플", "model": "iPhone 15 Pro", "category": "smartphone"}},
            "listing_data_jsonb": {"canonical_listing": {"title": "아이폰 판매", "price": 900000}},
        }
        row = session_to_price_history_row(session)
        assert row is not None
        assert row["brand"] == "Apple"
        assert row["model"] == "iPhone 15 Pro"
        assert row["category"] == "smartphone"
        assert row["price"] == 900000
        assert row["source_type"] == "sell_session"
        assert row["source_url"] == "session://session-1"
        assert row["platform"] == "sagupalgu_market"
        assert row["condition"] == "sold"

    @pytest.mark.unit
    def test_model_누락이면_None(self):
        from app.db.product_catalog_store import session_to_price_history_row
        session = {
            "id": "x",
            "product_data_jsonb": {"confirmed_product": {"brand": "Apple"}},
            "listing_data_jsonb": {"canonical_listing": {"price": 1000}},
        }
        assert session_to_price_history_row(session) is None

    @pytest.mark.unit
    def test_price_0이면_None(self):
        from app.db.product_catalog_store import session_to_price_history_row
        session = {
            "id": "x",
            "product_data_jsonb": {"confirmed_product": {"model": "iPhone"}},
            "listing_data_jsonb": {"canonical_listing": {"price": 0}},
        }
        assert session_to_price_history_row(session) is None

    @pytest.mark.unit
    def test_price_invalid_string이면_None(self):
        from app.db.product_catalog_store import session_to_price_history_row
        session = {
            "id": "x",
            "product_data_jsonb": {"confirmed_product": {"model": "iPhone"}},
            "listing_data_jsonb": {"canonical_listing": {"price": "abc"}},
        }
        assert session_to_price_history_row(session) is None

    @pytest.mark.unit
    def test_listing_제목_없으면_brand_model_조합(self):
        from app.db.product_catalog_store import session_to_price_history_row
        session = {
            "id": "x",
            "product_data_jsonb": {"confirmed_product": {"brand": "Samsung", "model": "Galaxy S24"}},
            "listing_data_jsonb": {"canonical_listing": {"price": 700000}},
        }
        row = session_to_price_history_row(session)
        assert row["title"] == "Samsung Galaxy S24"


# ── hybrid_search_catalog (cold_start + source_breakdown) ─────────────


class TestHybridSearchCatalog:
    """vector + keyword fallback. Supabase RPC + OpenAI embedding mock."""

    @pytest.mark.integration
    async def test_vector_hit_많음_cold_start_False(self):
        """3건 이상 + top_conf >= 0.5 → cold_start=False (CTO #4 명시 임계값)."""
        from app.db import product_catalog_store

        rpc_rows = [
            {"id": "1", "brand": "Apple", "model": "iPhone 15", "category": "smartphone",
             "title": "iPhone", "price": 900000, "platform": "bunjang",
             "condition": "good", "source_type": "crawled", "similarity": 0.85},
            {"id": "2", "brand": "Apple", "model": "iPhone 15 Pro", "category": "smartphone",
             "title": "iPhone Pro", "price": 1200000, "platform": "sagupalgu_market",
             "condition": "sold", "source_type": "sell_session", "similarity": 0.78},
            {"id": "3", "brand": "Apple", "model": "iPhone 15 Plus", "category": "smartphone",
             "title": "iPhone Plus", "price": 1000000, "platform": "joongna",
             "condition": "good", "source_type": "crawled", "similarity": 0.72},
        ]
        mock_supabase = MagicMock()
        mock_supabase.rpc.return_value.execute.return_value.data = rpc_rows

        with patch("app.db.product_catalog_store.get_embedding", new=AsyncMock(return_value=[0.1] * 1536)):
            with patch("app.db.client.get_supabase", return_value=mock_supabase):
                result = await product_catalog_store.hybrid_search_catalog(
                    "Apple", "iPhone 15", "smartphone", api_key="sk-test"
                )

        assert result["source_count"] == 3
        assert result["cold_start"] is False
        assert result["cold_start_reason"] is None
        assert result["fallback_path"] == "vector"
        assert result["top_match_confidence"] == pytest.approx(0.85)
        assert result["source_breakdown"]["crawled"] == 2
        assert result["source_breakdown"]["sell_session"] == 1

    @pytest.mark.integration
    async def test_vector_hit_적으면_cold_start_True_hit_count(self):
        """매치 2건뿐 (< 3) → cold_start=True (CTO #4: hit count 기준)."""
        from app.db import product_catalog_store

        rpc_rows = [
            {"id": "1", "brand": "Apple", "model": "iPhone 15", "category": "smartphone",
             "title": "iPhone", "price": 900000, "platform": "bunjang",
             "condition": "good", "source_type": "crawled", "similarity": 0.85},
            {"id": "2", "brand": "Apple", "model": "iPhone 15 Pro", "category": "smartphone",
             "title": "iPhone Pro", "price": 1200000, "platform": "sagupalgu_market",
             "condition": "sold", "source_type": "sell_session", "similarity": 0.78},
        ]
        mock_supabase = MagicMock()
        mock_supabase.rpc.return_value.execute.return_value.data = rpc_rows

        with patch("app.db.product_catalog_store.get_embedding", new=AsyncMock(return_value=[0.1] * 1536)):
            with patch("app.db.client.get_supabase", return_value=mock_supabase):
                result = await product_catalog_store.hybrid_search_catalog(
                    "Apple", "iPhone 15", "smartphone", api_key="sk-test"
                )

        assert result["source_count"] == 2
        assert result["cold_start"] is True
        assert "hit_count=2<3" in (result["cold_start_reason"] or "")

    @pytest.mark.integration
    async def test_top_conf_낮으면_cold_start_True_confidence(self):
        """top similarity < 0.5 → cold_start=True (CTO #4: confidence 기준)."""
        from app.db import product_catalog_store

        # 4건 (>= COLD_START_MIN_HITS) 이지만 top_conf 0.42 (< 0.5)
        rpc_rows = [
            {"id": str(i), "brand": "X", "model": "Y", "category": "etc",
             "title": "T", "price": 100, "platform": "p",
             "condition": "u", "source_type": "crawled", "similarity": 0.42 - i * 0.05}
            for i in range(4)
        ]
        mock_supabase = MagicMock()
        mock_supabase.rpc.return_value.execute.return_value.data = rpc_rows

        with patch("app.db.product_catalog_store.get_embedding", new=AsyncMock(return_value=[0.1] * 1536)):
            with patch("app.db.client.get_supabase", return_value=mock_supabase):
                result = await product_catalog_store.hybrid_search_catalog(
                    "X", "Y", "etc", api_key="sk-test"
                )

        assert result["source_count"] == 4
        assert result["cold_start"] is True
        assert "top_similarity" in (result["cold_start_reason"] or "")

    @pytest.mark.integration
    async def test_vector_0건이면_keyword_fallback(self):
        """vector RPC 빈결과 → keyword RPC fallback. fallback_path='keyword' 기록."""
        from app.db import product_catalog_store

        keyword_rows = [
            {"id": f"k{i}", "brand": "Apple", "model": "iPhone 15", "category": "smartphone",
             "title": "iPhone", "price": 900000, "platform": "bunjang",
             "condition": "unknown", "source_type": "crawled"}
            for i in range(3)
        ]
        mock_supabase = MagicMock()
        vector_call = MagicMock()
        vector_call.execute.return_value.data = []
        keyword_call = MagicMock()
        keyword_call.execute.return_value.data = keyword_rows
        mock_supabase.rpc.side_effect = [vector_call, keyword_call]

        with patch("app.db.product_catalog_store.get_embedding", new=AsyncMock(return_value=[0.1] * 1536)):
            with patch("app.db.client.get_supabase", return_value=mock_supabase):
                result = await product_catalog_store.hybrid_search_catalog(
                    "Apple", "iPhone 15", "smartphone", api_key="sk-test"
                )

        assert result["source_count"] == 3
        assert result["fallback_path"] == "keyword"
        assert mock_supabase.rpc.call_count == 2

    @pytest.mark.integration
    async def test_RPC_둘다_실패시_python_ilike_fallback(self):
        """CTO #2: RPC 자체가 깨졌을 때(migration 미적용) Python ILIKE 보루."""
        from app.db import product_catalog_store

        ilike_rows = [
            {"id": f"p{i}", "brand": "Apple", "model": "iPhone 15", "category": "smartphone",
             "title": "iPhone", "price": 900000, "platform": "bunjang",
             "condition": "unknown", "source_type": "crawled"}
            for i in range(3)
        ]
        mock_supabase = MagicMock()
        # 두 RPC 호출 모두 예외 (migration 미적용 시뮬레이션)
        mock_supabase.rpc.side_effect = Exception("function vector_search_catalog_hybrid does not exist")
        # .table().select().ilike()...execute()는 정상 동작
        table_chain = (
            mock_supabase.table.return_value
            .select.return_value
            .ilike.return_value
            .ilike.return_value
            .order.return_value
            .limit.return_value
        )
        table_chain.execute.return_value.data = ilike_rows

        with patch("app.db.product_catalog_store.get_embedding", new=AsyncMock(return_value=[0.1] * 1536)):
            with patch("app.db.client.get_supabase", return_value=mock_supabase):
                result = await product_catalog_store.hybrid_search_catalog(
                    "Apple", "iPhone 15", "", api_key="sk-test"
                )

        assert result["source_count"] == 3
        assert result["fallback_path"] == "python_ilike"

    @pytest.mark.integration
    async def test_cold_start_true_when_둘다_빈(self):
        """vector 0건 + keyword 0건 → cold_start=True."""
        from app.db import product_catalog_store

        mock_supabase = MagicMock()
        empty_call = MagicMock()
        empty_call.execute.return_value.data = []
        mock_supabase.rpc.return_value = empty_call

        with patch("app.db.product_catalog_store.get_embedding", new=AsyncMock(return_value=[0.1] * 1536)):
            with patch("app.db.client.get_supabase", return_value=mock_supabase):
                result = await product_catalog_store.hybrid_search_catalog(
                    "Unknown", "ZZZ", "etc", api_key="sk-test"
                )

        assert result["source_count"] == 0
        assert result["cold_start"] is True
        assert result["top_match_confidence"] == 0.0

    @pytest.mark.integration
    async def test_embedding_실패시_keyword_바로(self):
        """OpenAI 임베딩 실패 → vector 스킵 → keyword fallback."""
        from app.db import product_catalog_store

        mock_supabase = MagicMock()
        mock_supabase.rpc.return_value.execute.return_value.data = [
            {"id": "k1", "brand": "Samsung", "model": "Galaxy S24", "category": "phone",
             "title": "Galaxy", "price": 700000, "platform": "joongna",
             "condition": "unknown", "source_type": "crawled"},
        ]

        with patch("app.db.product_catalog_store.get_embedding", new=AsyncMock(return_value=None)):
            with patch("app.db.client.get_supabase", return_value=mock_supabase):
                result = await product_catalog_store.hybrid_search_catalog(
                    "Samsung", "Galaxy S24", "phone", api_key="sk-test"
                )

        # vector 스킵, keyword RPC만 호출됨
        assert mock_supabase.rpc.call_count == 1
        assert result["source_count"] == 1


# ── Sync Service incremental + 중복 skip ──────────────────────────────


class TestCatalogSync:
    @pytest.mark.integration
    async def test_dry_run은_insert_안함(self):
        from app.services import catalog_sync_service

        sessions = [
            {
                "id": "s1",
                "product_data_jsonb": {"confirmed_product": {"brand": "Apple", "model": "iPhone 15"}},
                "listing_data_jsonb": {"canonical_listing": {"price": 900000}},
                "updated_at": "2026-04-19T10:00:00+00:00",
            },
        ]
        mock_supabase = MagicMock()
        # cursor 읽기
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
            {"last_synced_at": "2026-04-18T00:00:00+00:00"}
        ]
        # sessions 조회
        sessions_chain = (
            mock_supabase.table.return_value
            .select.return_value
            .eq.return_value
            .filter.return_value
            .gt.return_value
            .order.return_value
            .limit.return_value
        )
        sessions_chain.execute.return_value.data = sessions
        # 중복 체크 — 빈 결과 (모두 신규)
        mock_supabase.table.return_value.select.return_value.in_.return_value.execute.return_value.data = []

        with patch("app.db.client.get_supabase", return_value=mock_supabase):
            result = await catalog_sync_service.sync_completed_sessions_to_price_history(
                api_key="sk-test", dry_run=True,
            )

        assert result["dry_run"] is True
        assert result["fetched"] == 1
        assert result["transformable"] == 1
        assert result["inserted"] == 0  # dry_run이라 0

    @pytest.mark.integration
    async def test_중복_skip_확인(self):
        """같은 source_url이 이미 있으면 skip."""
        from app.services import catalog_sync_service

        sessions = [
            {
                "id": "s1",
                "product_data_jsonb": {"confirmed_product": {"brand": "Apple", "model": "iPhone 15"}},
                "listing_data_jsonb": {"canonical_listing": {"price": 900000}},
                "updated_at": "2026-04-19T10:00:00+00:00",
            },
            {
                "id": "s2",
                "product_data_jsonb": {"confirmed_product": {"brand": "Samsung", "model": "Galaxy S24"}},
                "listing_data_jsonb": {"canonical_listing": {"price": 700000}},
                "updated_at": "2026-04-19T11:00:00+00:00",
            },
        ]
        mock_supabase = MagicMock()
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
            {"last_synced_at": "2026-04-18T00:00:00+00:00"}
        ]
        sessions_chain = (
            mock_supabase.table.return_value.select.return_value.eq.return_value
            .filter.return_value.gt.return_value.order.return_value.limit.return_value
        )
        sessions_chain.execute.return_value.data = sessions
        # 중복 체크 — s1은 이미 있음
        mock_supabase.table.return_value.select.return_value.in_.return_value.execute.return_value.data = [
            {"source_url": "session://s1"}
        ]

        with patch("app.db.client.get_supabase", return_value=mock_supabase):
            result = await catalog_sync_service.sync_completed_sessions_to_price_history(
                api_key="sk-test", dry_run=True,
            )

        assert result["fetched"] == 2
        assert result["transformable"] == 2
        assert result["skipped_duplicate"] == 1   # s1만 중복
        assert result["inserted"] == 0

    @pytest.mark.integration
    async def test_빈_sessions면_cursor_그대로(self):
        from app.services import catalog_sync_service

        mock_supabase = MagicMock()
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
            {"last_synced_at": "2026-04-18T00:00:00+00:00"}
        ]
        sessions_chain = (
            mock_supabase.table.return_value.select.return_value.eq.return_value
            .filter.return_value.gt.return_value.order.return_value.limit.return_value
        )
        sessions_chain.execute.return_value.data = []

        with patch("app.db.client.get_supabase", return_value=mock_supabase):
            result = await catalog_sync_service.sync_completed_sessions_to_price_history(
                api_key="sk-test", dry_run=True,
            )

        assert result["fetched"] == 0
        assert result["cursor_advanced_to"] == "2026-04-18T00:00:00+00:00"
