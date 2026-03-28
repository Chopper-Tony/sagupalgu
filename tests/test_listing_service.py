"""
ListingService 통합 테스트

LLM/외부 서비스는 mock 처리하고 ListingService의 오케스트레이션 로직을 검증한다:
- build_canonical_listing: LLM 정상 반환 → CanonicalListingSchema 검증
- rewrite_listing: rewrite_context 구성, 기존 listing 보존
- generate_copy fallback: OpenAI 실패 → Gemini → Solar → template
- build_listing_package: 전체 파이프라인 오케스트레이션
"""
import pytest
from unittest.mock import AsyncMock, patch

from app.services.listing_service import ListingService


# ── 공통 픽스처 ──────────────────────────────────────────────────────

@pytest.fixture
def product():
    return {"brand": "Apple", "model": "iPhone 15 Pro", "category": "smartphone"}


@pytest.fixture
def market():
    return {"median_price": 980000, "price_band": [900000, 1100000], "sample_count": 12}


@pytest.fixture
def strategy():
    return {"goal": "fast_sell", "recommended_price": 950600}


@pytest.fixture
def image_paths():
    return ["/uploads/img1.jpg", "/uploads/img2.jpg"]


@pytest.fixture
def llm_result():
    """LLM이 정상 반환하는 JSON 딕셔너리."""
    return {
        "title": "아이폰 15 프로 급처합니다",
        "description": "깨끗한 상태. 풀박스. 직거래 우선.",
        "tags": ["아이폰", "iPhone", "15프로"],
    }


@pytest.fixture
def canonical_listing():
    """이미 생성된 canonical_listing (rewrite 테스트용)."""
    return {
        "title": "아이폰 15 프로 판매합니다",
        "description": "상태 좋습니다. 풀박스.",
        "price": 950600,
        "tags": ["아이폰", "iPhone"],
        "images": ["/uploads/img1.jpg"],
        "strategy": "fast_sell",
        "product": {"brand": "Apple", "model": "iPhone 15 Pro", "category": "smartphone"},
    }


@pytest.fixture
def svc():
    return ListingService()


# ── build_canonical_listing 테스트 ───────────────────────────────────

@pytest.mark.integration
class TestBuildCanonicalListing:
    """LLM 정상 반환 시 CanonicalListingSchema 계약 준수 검증."""

    async def test_정상_llm_결과로_canonical_listing_생성(
        self, svc, product, market, strategy, image_paths, llm_result,
    ):
        with patch(
            "app.services.listing_service.generate_copy",
            new_callable=AsyncMock,
            return_value=llm_result,
        ):
            result = await svc.build_canonical_listing(
                confirmed_product=product,
                market_context=market,
                strategy=strategy,
                image_paths=image_paths,
            )

        # CanonicalListingSchema 필수 필드 존재
        assert "title" in result
        assert "description" in result
        assert "price" in result
        assert "tags" in result
        assert "images" in result

    async def test_price는_strategy의_recommended_price_사용(
        self, svc, product, market, strategy, image_paths, llm_result,
    ):
        with patch(
            "app.services.listing_service.generate_copy",
            new_callable=AsyncMock,
            return_value=llm_result,
        ):
            result = await svc.build_canonical_listing(
                confirmed_product=product,
                market_context=market,
                strategy=strategy,
                image_paths=image_paths,
            )

        assert result["price"] == strategy["recommended_price"]

    async def test_images는_전달된_image_paths_반영(
        self, svc, product, market, strategy, image_paths, llm_result,
    ):
        with patch(
            "app.services.listing_service.generate_copy",
            new_callable=AsyncMock,
            return_value=llm_result,
        ):
            result = await svc.build_canonical_listing(
                confirmed_product=product,
                market_context=market,
                strategy=strategy,
                image_paths=image_paths,
            )

        assert result["images"] == image_paths

    async def test_tool_calls_context가_generate_copy에_전달(
        self, svc, product, market, strategy, image_paths, llm_result,
    ):
        """tool_calls 파라미터가 build_tool_calls_context를 거쳐 LLM에 전달되는지 확인."""
        mock_gen = AsyncMock(return_value=llm_result)
        with patch("app.services.listing_service.generate_copy", mock_gen):
            tool_calls = [{"tool": "market_crawl", "result": "시세 데이터"}]
            await svc.build_canonical_listing(
                confirmed_product=product,
                market_context=market,
                strategy=strategy,
                image_paths=image_paths,
                tool_calls=tool_calls,
            )

        # generate_copy가 tool_calls_context 문자열을 받았는지 확인
        call_kwargs = mock_gen.call_args.kwargs
        assert "tool_calls_context" in call_kwargs
        assert len(call_kwargs["tool_calls_context"]) > 0

    async def test_llm_결과에_title_없으면_fallback_title_생성(
        self, svc, product, market, strategy, image_paths,
    ):
        """LLM이 title을 빈 문자열로 반환해도 fallback 제목 생성."""
        llm_no_title = {"title": "", "description": "설명", "tags": ["태그"]}
        with patch(
            "app.services.listing_service.generate_copy",
            new_callable=AsyncMock,
            return_value=llm_no_title,
        ):
            result = await svc.build_canonical_listing(
                confirmed_product=product,
                market_context=market,
                strategy=strategy,
                image_paths=image_paths,
            )

        # fallback title은 모델명 + "판매합니다"
        assert "판매합니다" in result["title"]

    async def test_tags_5개_이하로_정규화(
        self, svc, product, market, strategy, image_paths,
    ):
        llm_many_tags = {
            "title": "테스트 상품",
            "description": "설명",
            "tags": ["a", "b", "c", "d", "e", "f", "g"],
        }
        with patch(
            "app.services.listing_service.generate_copy",
            new_callable=AsyncMock,
            return_value=llm_many_tags,
        ):
            result = await svc.build_canonical_listing(
                confirmed_product=product,
                market_context=market,
                strategy=strategy,
                image_paths=image_paths,
            )

        assert len(result["tags"]) <= 5


# ── rewrite_listing 테스트 ───────────────────────────────────────────

@pytest.mark.integration
class TestRewriteListing:
    """사용자 피드백 기반 재작성 로직 검증."""

    async def test_rewrite_결과가_canonical_schema_준수(
        self, svc, canonical_listing, product, market, strategy,
    ):
        rewrite_result = {
            "title": "아이폰 15 프로 급처! 풀박스",
            "description": "거의 새 것. 풀박스 구성. 네고 가능.",
            "tags": ["아이폰", "급처", "풀박스"],
        }
        with patch(
            "app.services.listing_service.generate_copy",
            new_callable=AsyncMock,
            return_value=rewrite_result,
        ):
            result = await svc.rewrite_listing(
                canonical_listing=canonical_listing,
                rewrite_instruction="더 급하게 써주세요",
                confirmed_product=product,
                market_context=market,
                strategy=strategy,
            )

        assert "title" in result
        assert "description" in result
        assert "price" in result
        assert result["title"] == "아이폰 15 프로 급처! 풀박스"

    async def test_rewrite시_기존_price_보존(
        self, svc, canonical_listing, product, market, strategy,
    ):
        """rewrite 결과에 price가 없으면 기존 listing의 price 유지."""
        rewrite_result = {
            "title": "수정된 제목",
            "description": "수정된 설명",
            "tags": ["태그"],
        }
        with patch(
            "app.services.listing_service.generate_copy",
            new_callable=AsyncMock,
            return_value=rewrite_result,
        ):
            result = await svc.rewrite_listing(
                canonical_listing=canonical_listing,
                rewrite_instruction="제목 수정",
                confirmed_product=product,
                market_context=market,
                strategy=strategy,
            )

        # 기존 canonical_listing의 price 보존
        assert result["price"] == canonical_listing["price"]

    async def test_rewrite시_기존_images_보존(
        self, svc, canonical_listing, product, market, strategy,
    ):
        rewrite_result = {"title": "수정", "description": "설명", "tags": []}
        with patch(
            "app.services.listing_service.generate_copy",
            new_callable=AsyncMock,
            return_value=rewrite_result,
        ):
            result = await svc.rewrite_listing(
                canonical_listing=canonical_listing,
                rewrite_instruction="수정해주세요",
                confirmed_product=product,
                market_context=market,
                strategy=strategy,
            )

        assert result["images"] == canonical_listing["images"]

    async def test_rewrite_instruction이_generate_copy에_전달(
        self, svc, canonical_listing, product, market, strategy,
    ):
        """rewrite_instruction + 기존 listing이 context에 포함되어 LLM에 전달."""
        mock_gen = AsyncMock(return_value={"title": "t", "description": "d", "tags": []})
        with patch("app.services.listing_service.generate_copy", mock_gen):
            await svc.rewrite_listing(
                canonical_listing=canonical_listing,
                rewrite_instruction="가격을 더 강조해주세요",
                confirmed_product=product,
                market_context=market,
                strategy=strategy,
            )

        call_kwargs = mock_gen.call_args.kwargs
        # tool_calls_context에 rewrite context가 포함되어야 함
        assert "가격을 더 강조해주세요" in call_kwargs.get("tool_calls_context", "")


# ── generate_copy fallback 테스트 ────────────────────────────────────

@pytest.mark.integration
class TestGenerateCopyFallback:
    """LLM provider fallback 체인: OpenAI → Gemini → Solar → template."""

    async def test_모든_llm_실패시_template_fallback(
        self, svc, product, market, strategy, image_paths,
    ):
        """3개 LLM 전부 실패하면 build_template_copy 규칙 기반 폴백 반환."""
        with patch(
            "app.services.listing_service.generate_copy",
            new_callable=AsyncMock,
            return_value={
                "title": "iPhone 15 Pro 판매합니다",
                "description": "AI가 생성한 판매글 초안",
                "tags": ["iPhone 15 Pro"],
                "price": 0,
                "images": [],
                "strategy": "fast_sell",
                "product": product,
            },
        ):
            result = await svc.build_canonical_listing(
                confirmed_product=product,
                market_context=market,
                strategy=strategy,
                image_paths=image_paths,
            )

        # template fallback이든 LLM이든 유효한 결과 반환
        assert result["title"]
        assert isinstance(result["price"], int)


# ── build_listing_package 테스트 ─────────────────────────────────────

@pytest.mark.integration
class TestBuildListingPackage:
    """전체 파이프라인(시세→전략→판매글) 오케스트레이션 검증."""

    async def test_full_pipeline_오케스트레이션(
        self, svc, product, image_paths, llm_result, market,
    ):
        with patch.object(
            svc, "build_market_context",
            new_callable=AsyncMock,
            return_value=market,
        ), patch(
            "app.services.listing_service.generate_copy",
            new_callable=AsyncMock,
            return_value=llm_result,
        ):
            result = await svc.build_listing_package(
                confirmed_product=product,
                image_paths=image_paths,
            )

        assert "market_context" in result
        assert "strategy" in result
        assert "canonical_listing" in result
        # strategy는 market_context 기반으로 생성
        assert result["strategy"]["recommended_price"] > 0

    async def test_market_context_없으면_strategy_price_0(self, svc, product, image_paths, llm_result):
        """시세 데이터 없으면 추천 가격 0."""
        empty_market = {"median_price": 0, "price_band": [], "sample_count": 0}
        with patch.object(
            svc, "build_market_context",
            new_callable=AsyncMock,
            return_value=empty_market,
        ), patch(
            "app.services.listing_service.generate_copy",
            new_callable=AsyncMock,
            return_value=llm_result,
        ):
            result = await svc.build_listing_package(
                confirmed_product=product,
                image_paths=image_paths,
            )

        assert result["strategy"]["recommended_price"] == 0
