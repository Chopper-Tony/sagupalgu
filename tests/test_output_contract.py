"""
출력 계약 회귀 테스트.

CanonicalListingSchema를 경유하는 모든 경로가
동일한 shape(title, description, price, tags, images, strategy, product)를
보장하는지 검증한다.

경로:
1. from_llm_result — 최초 생성 (LLM 정상 응답)
2. from_rewrite_result — 재작성 (LLM 정상 응답)
3. from_llm_result — LLM 부분 누락 시 fallback
4. from_rewrite_result — LLM 부분 누락 시 fallback
5. build_template_copy — LLM 전체 실패 시 규칙 기반 폴백
6. coerce_price — 비정상 price 값 안전 처리
"""
import pytest
from pydantic import ValidationError

from app.domain.schemas import CanonicalListingSchema
from app.services.listing_llm import build_template_copy

REQUIRED_KEYS = {"title", "description", "price", "tags", "images", "strategy", "product"}

CONFIRMED_PRODUCT = {"brand": "Samsung", "model": "갤럭시 S24", "category": "smartphone", "confidence": 0.95}
STRATEGY = {"goal": "fast_sell", "recommended_price": 850000, "negotiation_policy": "small"}
IMAGE_PATHS = ["https://example.com/img1.jpg", "https://example.com/img2.jpg"]
MARKET_CONTEXT = {"median_price": 900000, "price_band": [800000, 900000, 1000000], "sample_count": 5}


class TestCanonicalListingFromLLM:
    """경로 1: from_llm_result — LLM 정상 응답."""

    @pytest.mark.unit
    def test_full_llm_result_produces_all_keys(self):
        llm_result = {"title": "갤럭시 S24 팝니다", "description": "상태 좋음", "tags": ["갤럭시", "S24"]}
        schema = CanonicalListingSchema.from_llm_result(
            llm_result, confirmed_product=CONFIRMED_PRODUCT, strategy=STRATEGY, image_paths=IMAGE_PATHS,
        )
        dumped = schema.model_dump()
        assert REQUIRED_KEYS <= set(dumped.keys())

    @pytest.mark.unit
    def test_price_comes_from_strategy(self):
        llm_result = {"title": "테스트", "description": "설명"}
        schema = CanonicalListingSchema.from_llm_result(
            llm_result, confirmed_product=CONFIRMED_PRODUCT, strategy=STRATEGY, image_paths=IMAGE_PATHS,
        )
        assert schema.price == 850000

    @pytest.mark.unit
    def test_images_come_from_image_paths(self):
        llm_result = {"title": "테스트", "description": "설명"}
        schema = CanonicalListingSchema.from_llm_result(
            llm_result, confirmed_product=CONFIRMED_PRODUCT, strategy=STRATEGY, image_paths=IMAGE_PATHS,
        )
        assert schema.images == IMAGE_PATHS

    @pytest.mark.unit
    def test_product_preserved(self):
        llm_result = {"title": "테스트", "description": "설명"}
        schema = CanonicalListingSchema.from_llm_result(
            llm_result, confirmed_product=CONFIRMED_PRODUCT, strategy=STRATEGY, image_paths=[],
        )
        assert schema.product["brand"] == "Samsung"


class TestCanonicalListingFromRewrite:
    """경로 2: from_rewrite_result — 재작성."""

    @pytest.mark.unit
    def test_rewrite_produces_all_keys(self):
        llm_result = {"title": "수정된 제목", "description": "수정된 설명", "tags": ["수정"]}
        previous = {"title": "원본", "description": "원본설명", "price": 850000, "tags": ["원본"],
                     "images": IMAGE_PATHS, "strategy": "fast_sell", "product": CONFIRMED_PRODUCT}
        schema = CanonicalListingSchema.from_rewrite_result(
            llm_result, previous=previous, strategy=STRATEGY,
        )
        dumped = schema.model_dump()
        assert REQUIRED_KEYS <= set(dumped.keys())

    @pytest.mark.unit
    def test_rewrite_preserves_price_from_previous(self):
        llm_result = {"title": "수정됨", "description": "수정됨"}
        previous = {"title": "원본", "description": "원본", "price": 750000, "tags": [],
                     "images": [], "strategy": "fast_sell", "product": {}}
        schema = CanonicalListingSchema.from_rewrite_result(
            llm_result, previous=previous, strategy=STRATEGY,
        )
        assert schema.price == 750000

    @pytest.mark.unit
    def test_rewrite_preserves_images_from_previous(self):
        llm_result = {"title": "수정됨", "description": "수정됨"}
        previous = {"title": "원본", "description": "원본", "price": 850000, "tags": [],
                     "images": IMAGE_PATHS, "strategy": "fast_sell", "product": {}}
        schema = CanonicalListingSchema.from_rewrite_result(
            llm_result, previous=previous, strategy=STRATEGY,
        )
        assert schema.images == IMAGE_PATHS


class TestCanonicalListingFallback:
    """경로 3·4: LLM 부분 누락 시 fallback."""

    @pytest.mark.unit
    def test_missing_title_uses_model_name(self):
        llm_result = {"description": "설명만 있음"}
        schema = CanonicalListingSchema.from_llm_result(
            llm_result, confirmed_product=CONFIRMED_PRODUCT, strategy=STRATEGY, image_paths=[],
        )
        assert "갤럭시 S24" in schema.title

    @pytest.mark.unit
    def test_missing_description_uses_default(self):
        llm_result = {"title": "제목만 있음"}
        schema = CanonicalListingSchema.from_llm_result(
            llm_result, confirmed_product=CONFIRMED_PRODUCT, strategy=STRATEGY, image_paths=[],
        )
        assert len(schema.description) > 0

    @pytest.mark.unit
    def test_empty_tags_uses_model_name(self):
        llm_result = {"title": "제목", "description": "설명", "tags": []}
        schema = CanonicalListingSchema.from_llm_result(
            llm_result, confirmed_product=CONFIRMED_PRODUCT, strategy=STRATEGY, image_paths=[],
        )
        assert len(schema.tags) >= 1

    @pytest.mark.unit
    def test_rewrite_missing_title_falls_back_to_previous(self):
        llm_result = {"description": "수정된 설명만"}
        previous = {"title": "원본 제목", "description": "원본", "price": 850000, "tags": [],
                     "images": [], "strategy": "fast_sell", "product": {}}
        schema = CanonicalListingSchema.from_rewrite_result(
            llm_result, previous=previous, strategy=STRATEGY,
        )
        assert schema.title == "원본 제목"


class TestBuildTemplateCopy:
    """경로 5: build_template_copy — 규칙 기반 폴백."""

    @pytest.mark.unit
    def test_template_produces_all_keys(self):
        result = build_template_copy(CONFIRMED_PRODUCT, MARKET_CONTEXT, STRATEGY)
        assert REQUIRED_KEYS <= set(result.keys())

    @pytest.mark.unit
    def test_template_title_contains_model(self):
        result = build_template_copy(CONFIRMED_PRODUCT, MARKET_CONTEXT, STRATEGY)
        assert "갤럭시 S24" in result["title"]

    @pytest.mark.unit
    def test_template_price_equals_recommended(self):
        result = build_template_copy(CONFIRMED_PRODUCT, MARKET_CONTEXT, STRATEGY)
        assert result["price"] == 850000

    @pytest.mark.unit
    def test_template_tags_not_empty(self):
        result = build_template_copy(CONFIRMED_PRODUCT, MARKET_CONTEXT, STRATEGY)
        assert len(result["tags"]) >= 1

    @pytest.mark.unit
    def test_template_unknown_brand_excluded_from_title(self):
        product = {**CONFIRMED_PRODUCT, "brand": "Unknown"}
        result = build_template_copy(product, MARKET_CONTEXT, STRATEGY)
        assert "Unknown" not in result["title"]


class TestPriceCoercion:
    """경로 6: 비정상 price 값 안전 처리."""

    @pytest.mark.unit
    def test_string_price_coerced(self):
        schema = CanonicalListingSchema(title="테스트", description="설명", price="850000")
        assert schema.price == 850000

    @pytest.mark.unit
    def test_negative_price_clamped_to_zero(self):
        schema = CanonicalListingSchema(title="테스트", description="설명", price=-100)
        assert schema.price == 0

    @pytest.mark.unit
    def test_none_price_becomes_zero(self):
        schema = CanonicalListingSchema(title="테스트", description="설명", price=None)
        assert schema.price == 0

    @pytest.mark.unit
    def test_non_numeric_price_becomes_zero(self):
        schema = CanonicalListingSchema(title="테스트", description="설명", price="abc")
        assert schema.price == 0

    @pytest.mark.unit
    def test_empty_title_rejected(self):
        with pytest.raises(ValidationError):
            CanonicalListingSchema(title="", description="설명", price=1000)

    @pytest.mark.unit
    def test_whitespace_title_rejected(self):
        with pytest.raises(ValidationError):
            CanonicalListingSchema(title="   ", description="설명", price=1000)


class TestTagsNormalization:
    """tags 정규화 검증."""

    @pytest.mark.unit
    def test_tags_limited_to_5(self):
        schema = CanonicalListingSchema(
            title="테스트", description="설명", price=1000,
            tags=["a", "b", "c", "d", "e", "f", "g"],
        )
        assert len(schema.tags) == 5

    @pytest.mark.unit
    def test_empty_string_tags_stripped(self):
        schema = CanonicalListingSchema(
            title="테스트", description="설명", price=1000,
            tags=["valid", "", "  ", "also_valid"],
        )
        assert "" not in schema.tags
        assert len(schema.tags) == 2

    @pytest.mark.unit
    def test_non_list_tags_coerced(self):
        schema = CanonicalListingSchema(
            title="테스트", description="설명", price=1000,
            tags="single_tag",
        )
        assert schema.tags == ["single_tag"]
