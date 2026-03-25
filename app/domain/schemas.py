"""
도메인 스키마 — 핵심 데이터 구조의 Pydantic 계약.

CanonicalListingSchema: listing_service / session_service 사이를 오가는
canonical_listing 딕셔너리의 shape를 강제한다.
"""
from __future__ import annotations

from typing import Any, Dict, List

from pydantic import BaseModel, field_validator


class CanonicalListingSchema(BaseModel):
    """판매글 정규 스키마. LLM 출력 직후 validate_from_dict()를 통해 생성."""

    title: str
    description: str
    price: int
    tags: List[str] = []
    images: List[str] = []
    strategy: str = "balanced"
    product: Dict[str, Any] = {}

    @field_validator("title")
    @classmethod
    def title_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("title은 비어있을 수 없습니다")
        return v.strip()

    @field_validator("tags", mode="before")
    @classmethod
    def normalize_tags(cls, v: Any) -> List[str]:
        if not isinstance(v, list):
            v = [str(v)] if v else []
        return [str(t).strip() for t in v if str(t).strip()][:5]

    @field_validator("price", mode="before")
    @classmethod
    def coerce_price(cls, v: Any) -> int:
        try:
            return max(0, int(v))
        except (TypeError, ValueError):
            return 0

    @classmethod
    def from_llm_result(
        cls,
        llm_result: Dict[str, Any],
        *,
        confirmed_product: Dict[str, Any],
        strategy: Dict[str, Any],
        image_paths: List[str],
    ) -> "CanonicalListingSchema":
        """LLM 딕셔너리 + 컨텍스트를 받아 검증된 스키마 인스턴스 반환."""
        title = (
            llm_result.get("title")
            or f"{confirmed_product.get('model', '상품')} 판매합니다"
        )
        description = llm_result.get("description") or "AI가 생성한 판매글 초안"
        tags = llm_result.get("tags") or [confirmed_product.get("model", "상품")]

        return cls(
            title=title,
            description=description,
            price=strategy.get("recommended_price", 0),
            tags=tags,
            images=image_paths,
            strategy=strategy.get("goal", "fast_sell"),
            product=confirmed_product,
        )

    @classmethod
    def from_rewrite_result(
        cls,
        llm_result: Dict[str, Any],
        *,
        previous: Dict[str, Any],
        strategy: Dict[str, Any],
    ) -> "CanonicalListingSchema":
        """재작성 LLM 결과 + 이전 listing으로 검증된 스키마 인스턴스 반환."""
        title = llm_result.get("title") or previous.get("title", "")
        description = llm_result.get("description") or previous.get("description", "")
        tags = llm_result.get("tags") or previous.get("tags") or []
        price = previous.get("price") or strategy.get("recommended_price", 0)

        return cls(
            title=title,
            description=description,
            price=price,
            tags=tags,
            images=previous.get("images") or [],
            strategy=previous.get("strategy") or strategy.get("goal", "fast_sell"),
            product=previous.get("product") or {},
        )
