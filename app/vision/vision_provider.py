from dataclasses import dataclass
from typing import Protocol

@dataclass
class ProductIdentityResult:
    candidates: list[dict]
    confirmed_hint: dict | None = None
    raw_response: dict | None = None

class VisionProvider(Protocol):
    async def identify_product(self, images: list[str]) -> ProductIdentityResult:
        ...
