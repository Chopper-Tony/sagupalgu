from app.builders.package_builder import PackageBuilder

class JoongnaPackageBuilder(PackageBuilder):
    def build(self, canonical_listing: dict) -> dict:
        return {
            "platform": "joongna",
            "product_name": canonical_listing.get("product", {}).get("model") or canonical_listing.get("title", ""),
            "title": canonical_listing.get("title", ""),
            "body": canonical_listing.get("description", ""),
            "price": canonical_listing.get("price", 0),
            "images": canonical_listing.get("images", []),
            "tags": canonical_listing.get("tags", []),
            "category": canonical_listing.get("product", {}).get("category", "기타"),
            "shipping_available": True,
            "shipping_fee": 3500,
            "negotiable": True,
        }
