from pathlib import Path

from app.publishers._legacy_compat import (
    ListingPackage as LegacyListingPackage,
    ProductCondition,
    SellStrategy,
)

def to_legacy_listing_package(payload: dict) -> LegacyListingPackage:
    image_paths = [Path(p) for p in payload.get("images", [])]
    return LegacyListingPackage(
        product_name=payload.get("product_name") or payload.get("title", "중고 상품"),
        category=payload.get("category", "기타"),
        condition=ProductCondition.GOOD,
        price=int(payload.get("price", 0)),
        title=payload.get("title", ""),
        description=payload.get("body") or payload.get("description", ""),
        tags=payload.get("tags", []),
        negotiable=payload.get("negotiable", True),
        shipping_available=payload.get("shipping_available", False),
        shipping_fee=int(payload.get("shipping_fee", 0)),
        meet_location=payload.get("meet_location", ""),
        image_paths=image_paths,
        strategy=SellStrategy.NORMAL,
    )
