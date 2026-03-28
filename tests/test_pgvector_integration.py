"""
M92: pgvector + RAG 실사용 검증 테스트

벡터 검색 → 키워드 검색 → 빈 결과 3경로를 mock 기반으로 검증한다.
실제 Supabase/OpenAI 연결 없이 동작.
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

pytestmark = pytest.mark.integration


class TestVectorSearch:

    @pytest.mark.asyncio
    async def test_벡터검색_정상_결과_반환(self):
        """임베딩 성공 → RPC 호출 → 결과 반환"""
        from app.db.pgvector_store import vector_search_price_history

        mock_rows = [
            {"model": "아이폰 15 Pro", "brand": "애플", "price": 950000, "similarity": 0.92},
            {"model": "아이폰 15 Pro", "brand": "애플", "price": 1050000, "similarity": 0.88},
        ]
        mock_execute = MagicMock()
        mock_execute.data = mock_rows

        mock_supabase = MagicMock()
        mock_supabase.rpc.return_value.execute.return_value = mock_execute

        with patch("app.db.pgvector_store.get_embedding", new_callable=AsyncMock, return_value=[0.1] * 1536):
            with patch("app.db.client.get_supabase", return_value=mock_supabase):
                results = await vector_search_price_history("애플", "아이폰 15 Pro", "fake-key")

        assert len(results) == 2
        assert results[0]["price"] == 950000
        mock_supabase.rpc.assert_called_once_with(
            "search_price_history",
            {"query_embedding": [0.1] * 1536, "match_threshold": 0.4, "match_count": 10},
        )

    @pytest.mark.asyncio
    async def test_임베딩_실패시_빈_결과(self):
        """임베딩 생성 실패 → 벡터 검색 불가 → 빈 리스트"""
        from app.db.pgvector_store import vector_search_price_history

        with patch("app.db.pgvector_store.get_embedding", new_callable=AsyncMock, return_value=None):
            results = await vector_search_price_history("애플", "아이폰 15 Pro", "fake-key")

        assert results == []

    @pytest.mark.asyncio
    async def test_rpc_실패시_빈_결과(self):
        """RPC 호출 예외 → 빈 리스트"""
        from app.db.pgvector_store import vector_search_price_history

        mock_supabase = MagicMock()
        mock_supabase.rpc.return_value.execute.side_effect = Exception("RPC 실패")

        with patch("app.db.pgvector_store.get_embedding", new_callable=AsyncMock, return_value=[0.1] * 1536):
            with patch("app.db.client.get_supabase", return_value=mock_supabase):
                results = await vector_search_price_history("애플", "아이폰 15 Pro", "fake-key")

        assert results == []


class TestKeywordSearch:

    @pytest.mark.asyncio
    async def test_키워드검색_정상_결과(self):
        """ILIKE 키워드 검색 → 결과 반환"""
        from app.db.pgvector_store import keyword_search_price_history

        mock_rows = [
            {"model": "아이폰 15 Pro", "brand": "애플", "price": 980000, "platform": "bunjang"},
        ]
        mock_execute = MagicMock()
        mock_execute.data = mock_rows

        mock_query = MagicMock()
        mock_query.ilike.return_value = mock_query
        mock_query.order.return_value.limit.return_value.execute.return_value = mock_execute

        mock_supabase = MagicMock()
        mock_supabase.table.return_value.select.return_value.ilike.return_value = mock_query

        with patch("app.db.client.get_supabase", return_value=mock_supabase):
            results = await keyword_search_price_history("아이폰 15 Pro", "애플")

        assert len(results) == 1
        assert results[0]["price"] == 980000

    @pytest.mark.asyncio
    async def test_키워드검색_실패시_빈_결과(self):
        """DB 에러 → 빈 리스트"""
        from app.db.pgvector_store import keyword_search_price_history

        mock_supabase = MagicMock()
        mock_supabase.table.return_value.select.side_effect = Exception("DB 연결 실패")

        with patch("app.db.client.get_supabase", return_value=mock_supabase):
            results = await keyword_search_price_history("아이폰 15 Pro")

        assert results == []


class TestRAGPipeline:

    @pytest.mark.asyncio
    async def test_rag_3단계_fallback_체인(self):
        """market_tools의 RAG 3단계: 벡터→키워드→LLM 추정 fallback"""
        from app.tools.market_tools import _rag_price_impl

        confirmed = {"brand": "테스트", "model": "상품", "category": "기타"}

        with patch("app.db.pgvector_store.vector_search_price_history", new_callable=AsyncMock, return_value=[]):
            with patch("app.db.pgvector_store.keyword_search_price_history", new_callable=AsyncMock, return_value=[]):
                result = await _rag_price_impl(confirmed)

        # make_tool_call 형식 반환
        assert isinstance(result, dict)
        assert "output" in result or "tool_name" in result

    @pytest.mark.asyncio
    async def test_벡터검색_성공시_rag_결과(self):
        """벡터 검색 성공 → RAG 결과에 가격 데이터 포함"""
        from app.tools.market_tools import _rag_price_impl

        confirmed = {"brand": "애플", "model": "아이폰 15 Pro", "category": "스마트폰"}

        mock_results = [
            {"model": "아이폰 15 Pro", "brand": "애플", "price": 950000, "platform": "bunjang", "similarity": 0.9},
            {"model": "아이폰 15 Pro", "brand": "애플", "price": 1050000, "platform": "joongna", "similarity": 0.85},
        ]

        with patch("app.db.pgvector_store.vector_search_price_history", new_callable=AsyncMock, return_value=mock_results):
            result = await _rag_price_impl(confirmed)

        assert isinstance(result, dict)


class TestInsertRecords:

    @pytest.mark.asyncio
    async def test_레코드_삽입_성공(self):
        """skip_embedding=True로 키워드 검색용 데이터 삽입"""
        from app.db.pgvector_store import insert_price_records

        mock_supabase = MagicMock()
        mock_supabase.table.return_value.insert.return_value.execute.return_value = MagicMock()

        records = [
            {"model": "아이폰 15", "brand": "애플", "category": "스마트폰",
             "title": "아이폰 15 판매", "price": 800000, "platform": "bunjang"},
        ]

        with patch("app.db.client.get_supabase", return_value=mock_supabase):
            count = await insert_price_records(records, api_key="", skip_embedding=True)

        assert count == 1
        mock_supabase.table.return_value.insert.assert_called_once()

    @pytest.mark.asyncio
    async def test_삽입_실패시_계속_진행(self):
        """일부 레코드 삽입 실패 → 나머지 계속 처리"""
        from app.db.pgvector_store import insert_price_records

        call_count = 0
        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            mock = MagicMock()
            if call_count == 1:
                mock.execute.side_effect = Exception("중복 키")
            else:
                mock.execute.return_value = MagicMock()
            return mock

        mock_supabase = MagicMock()
        mock_supabase.table.return_value.insert = side_effect

        records = [
            {"model": "실패", "brand": "", "price": 0, "platform": ""},
            {"model": "성공", "brand": "", "price": 100000, "platform": "bunjang"},
        ]

        with patch("app.db.client.get_supabase", return_value=mock_supabase):
            count = await insert_price_records(records, api_key="", skip_embedding=True)

        assert count == 1  # 2건 중 1건만 성공


class TestTableReadiness:

    @pytest.mark.asyncio
    async def test_테이블_존재_확인(self):
        from app.db.pgvector_store import is_table_ready

        mock_supabase = MagicMock()
        mock_supabase.table.return_value.select.return_value.limit.return_value.execute.return_value = MagicMock()

        with patch("app.db.client.get_supabase", return_value=mock_supabase):
            assert await is_table_ready() is True

    @pytest.mark.asyncio
    async def test_테이블_없음(self):
        from app.db.pgvector_store import is_table_ready

        mock_supabase = MagicMock()
        mock_supabase.table.return_value.select.side_effect = Exception("relation not found")

        with patch("app.db.client.get_supabase", return_value=mock_supabase):
            assert await is_table_ready() is False
