"""
중고 판매 게시글 공통 데이터 모델
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
from pathlib import Path


class ProductCondition(Enum):
    """상품 상태"""
    NEW = "미개봉"
    LIKE_NEW = "거의 새것"
    GOOD = "상태 좋음"
    FAIR = "보통"
    POOR = "상태 나쁨"


class SellStrategy(Enum):
    """판매 전략"""
    FAST = "빠른 판매"       # 시세보다 약간 낮게
    NORMAL = "적정가"        # 시세 그대로
    MAX_PROFIT = "최대 이익"  # 시세보다 약간 높게


class Platform(Enum):
    BUNJANG = "번개장터"
    JOONGNA = "중고나라"
    DAANGN = "당근마켓"


@dataclass
class ListingPackage:
    """
    AI Agent Layer가 생성한 플랫폼별 최종 판매 패키지
    LangGraph Router → Publisher Layer로 전달되는 단위
    """
    # 상품 기본 정보
    product_name: str                   # 예: "Apple AirPods Pro 2세대"
    category: str                       # 예: "디지털기기 > 이어폰/헤드폰"
    condition: ProductCondition = ProductCondition.GOOD
    price: int = 0                      # 원 단위
    original_price: Optional[int] = None

    # 컨텐츠 (Copywriting Agent 결과)
    title: str = ""
    description: str = ""
    tags: list[str] = field(default_factory=list)

    # 거래 조건
    negotiable: bool = True             # 가격 제안 가능 여부
    shipping_available: bool = False    # 택배 거래 가능 여부
    shipping_fee: int = 0              # 택배비 (0 = 무료)
    meet_location: str = ""            # 직거래 희망 장소

    # 미디어
    image_paths: list[Path] = field(default_factory=list)

    # 플랫폼별 오버라이드 (없으면 공통값 사용)
    platform_overrides: dict = field(default_factory=dict)

    # 메타
    strategy: SellStrategy = SellStrategy.NORMAL

    def for_platform(self, platform: Platform) -> "ListingPackage":
        """플랫폼별 오버라이드 적용한 복사본 반환"""
        overrides = self.platform_overrides.get(platform.value, {})
        if not overrides:
            return self
        import copy
        copy_pkg = copy.deepcopy(self)
        for k, v in overrides.items():
            if hasattr(copy_pkg, k):
                setattr(copy_pkg, k, v)
        return copy_pkg


@dataclass
class PublishResult:
    """게시 결과"""
    platform: Platform
    success: bool
    listing_url: Optional[str] = None
    listing_id: Optional[str] = None
    error_message: Optional[str] = None
    screenshot_path: Optional[Path] = None

    def __repr__(self):
        status = "✅ 성공" if self.success else f"❌ 실패: {self.error_message}"
        return f"[{self.platform.value}] {status}" + (f" → {self.listing_url}" if self.listing_url else "")
