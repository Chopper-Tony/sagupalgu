"""
M106: Market 서비스 유닛 테스트

QueryBuilder, RelevanceScorer, PriceAggregator — 순수 함수, mock 불필요.
"""
import pytest

pytestmark = pytest.mark.unit


# ── QueryBuilder ─────────────────────────────────────────────────


class TestQueryBuilder:

    def test_model만_있으면_기본_쿼리(self):
        from app.services.market.query_builder import QueryBuilder
        queries = QueryBuilder.build_queries({"model": "iPhone 15 Pro"})
        assert "iPhone 15 Pro" in queries

    def test_compact_변환_추가(self):
        from app.services.market.query_builder import QueryBuilder
        queries = QueryBuilder.build_queries({"model": "iPhone 15 Pro"})
        assert "iPhone15Pro" in queries

    def test_compact_동일하면_중복_없음(self):
        from app.services.market.query_builder import QueryBuilder
        queries = QueryBuilder.build_queries({"model": "AirPods"})
        assert queries.count("AirPods") == 1

    def test_brand_model_조합(self):
        from app.services.market.query_builder import QueryBuilder
        queries = QueryBuilder.build_queries({"brand": "Apple", "model": "iPhone 15"})
        assert "Apple iPhone 15" in queries

    def test_model_storage_조합(self):
        from app.services.market.query_builder import QueryBuilder
        queries = QueryBuilder.build_queries({"model": "iPhone 15", "storage": "256GB"})
        assert "iPhone 15 256GB" in queries

    def test_brand_model_storage_전체(self):
        from app.services.market.query_builder import QueryBuilder
        queries = QueryBuilder.build_queries({
            "brand": "Apple", "model": "iPhone 15 Pro", "storage": "256GB",
        })
        assert "Apple iPhone 15 Pro 256GB" in queries

    def test_빈_product_빈_리스트(self):
        from app.services.market.query_builder import QueryBuilder
        queries = QueryBuilder.build_queries({})
        assert queries == []

    def test_category만_있으면_category_쿼리(self):
        from app.services.market.query_builder import QueryBuilder
        queries = QueryBuilder.build_queries({"category": "스마트폰"})
        assert "스마트폰" in queries

    def test_중복_제거(self):
        from app.services.market.query_builder import QueryBuilder
        queries = QueryBuilder.build_queries({"brand": "Apple", "model": "AirPods"})
        assert len(queries) == len(set(queries))

    def test_빈_문자열_제거(self):
        from app.services.market.query_builder import QueryBuilder
        queries = QueryBuilder.build_queries({"model": "  ", "brand": ""})
        assert all(q.strip() for q in queries)


# ── RelevanceScorer ──────────────────────────────────────────────


class TestRelevanceScorer:

    def test_model_일치_0점7(self):
        from app.services.market.relevance_scorer import RelevanceScorer
        score = RelevanceScorer.score(
            {"model": "iPhone 15 Pro"},
            {"title": "아이폰 iPhone 15 Pro 256GB 판매"},
        )
        assert score >= 0.7

    def test_brand_일치_0점2(self):
        from app.services.market.relevance_scorer import RelevanceScorer
        score = RelevanceScorer.score(
            {"brand": "Apple", "model": "없는모델"},
            {"title": "Apple 제품 판매합니다"},
        )
        assert 0.15 <= score <= 0.25

    def test_storage_일치_가산(self):
        from app.services.market.relevance_scorer import RelevanceScorer
        score_with = RelevanceScorer.score(
            {"model": "iPhone 15", "storage": "256GB"},
            {"title": "iPhone 15 256GB"},
        )
        score_without = RelevanceScorer.score(
            {"model": "iPhone 15", "storage": "256GB"},
            {"title": "iPhone 15 128GB"},
        )
        assert score_with > score_without

    def test_미일치_0점(self):
        from app.services.market.relevance_scorer import RelevanceScorer
        score = RelevanceScorer.score(
            {"model": "Galaxy S24"},
            {"title": "에어팟 프로 판매"},
        )
        assert score == 0.0

    def test_정규화_공백_하이픈(self):
        from app.services.market.relevance_scorer import RelevanceScorer
        score = RelevanceScorer.score(
            {"model": "iPhone-15 Pro"},
            {"title": "iphone15pro 팝니다"},
        )
        assert score >= 0.7

    def test_대소문자_무시(self):
        from app.services.market.relevance_scorer import RelevanceScorer
        score = RelevanceScorer.score(
            {"model": "MacBook Air"},
            {"title": "macbookair m3 판매"},
        )
        assert score >= 0.7

    def test_빈_title_0점(self):
        from app.services.market.relevance_scorer import RelevanceScorer
        score = RelevanceScorer.score(
            {"model": "iPhone 15"},
            {"title": ""},
        )
        assert score == 0.0


# ── PriceAggregator ──────────────────────────────────────────────


class TestPriceAggregator:

    def test_빈_리스트_none(self):
        from app.services.market.price_aggregator import PriceAggregator
        result = PriceAggregator.aggregate([])
        assert result["median_price"] is None
        assert result["sample_count"] == 0

    def test_가격_없는_항목_무시(self):
        from app.services.market.price_aggregator import PriceAggregator
        result = PriceAggregator.aggregate([
            {"title": "상품1"},
            {"title": "상품2", "price": None},
        ])
        assert result["sample_count"] == 0

    def test_정상_가격_집계(self):
        from app.services.market.price_aggregator import PriceAggregator
        result = PriceAggregator.aggregate([
            {"price": 900000},
            {"price": 1000000},
            {"price": 1100000},
        ])
        assert result["median_price"] == 1000000
        assert result["sample_count"] == 3
        assert result["price_band"] == [900000, 1100000]

    def test_이상치_필터링(self):
        from app.services.market.price_aggregator import PriceAggregator
        result = PriceAggregator.aggregate([
            {"price": 900000},
            {"price": 1000000},
            {"price": 1100000},
            {"price": 5000000},  # 이상치
        ])
        assert result["sample_count"] == 3
        assert 5000000 not in result["price_band"]

    def test_단일_가격(self):
        from app.services.market.price_aggregator import PriceAggregator
        result = PriceAggregator.aggregate([{"price": 500000}])
        assert result["median_price"] == 500000
        assert result["sample_count"] == 1

    def test_모두_이상치면_전체_사용(self):
        from app.services.market.price_aggregator import PriceAggregator
        # median=500000, 0.5*median=250000, 1.5*median=750000
        # 100000과 1000000 둘 다 이상치 → filtered 비어서 전체 사용
        result = PriceAggregator.aggregate([
            {"price": 100000},
            {"price": 1000000},
        ])
        assert result["sample_count"] == 2

    def test_band_최소_최대(self):
        from app.services.market.price_aggregator import PriceAggregator
        result = PriceAggregator.aggregate([
            {"price": 800000},
            {"price": 900000},
            {"price": 1000000},
        ])
        assert result["price_band"][0] == 800000
        assert result["price_band"][1] == 1000000

    def test_median_정수_반환(self):
        from app.services.market.price_aggregator import PriceAggregator
        result = PriceAggregator.aggregate([
            {"price": 999999},
            {"price": 1000001},
        ])
        assert isinstance(result["median_price"], int)
