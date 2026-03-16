from dataclasses import dataclass
from typing import Protocol, Any

@dataclass
class PlatformPackage:
    platform: str
    payload: dict[str, Any]

@dataclass
class PublisherAccountContext:
    platform_account_id: str
    platform: str
    auth_type: str
    secret_payload: dict[str, Any]

@dataclass
class PublishResult:
    success: bool
    platform: str
    external_listing_id: str | None = None
    external_url: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    evidence_path: str | None = None

class PlatformPublisher(Protocol):
    async def publish(self, package: PlatformPackage, account: PublisherAccountContext) -> PublishResult:
        ...
