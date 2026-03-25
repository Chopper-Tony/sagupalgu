"""
Legacy spike 의존성 단일 진입점.

app/publishers/ 및 app/crawlers/에서 legacy_spikes를 직접 import하지 않고,
이 모듈을 경유한다. 향후 legacy 코드를 app/ 내부로 흡수할 때 이 파일만 수정.
"""

# ── 크롤러 ────────────────────────────────────────────────────
try:
    from legacy_spikes.secondhand_publisher.utils.market_crawler import (
        MarketCrawler,
    )
except ImportError:
    MarketCrawler = None  # type: ignore[assignment, misc]

# ── Publisher 구현체 ──────────────────────────────────────────
try:
    from legacy_spikes.secondhand_publisher.publishers.bunjang import (
        BunjangPublisher as LegacyBunjangPublisher,
    )
except ImportError:
    LegacyBunjangPublisher = None  # type: ignore[assignment, misc]

try:
    from legacy_spikes.secondhand_publisher.publishers.joongna import (
        JoongnaPublisher as LegacyJoongnaPublisher,
    )
except ImportError:
    LegacyJoongnaPublisher = None  # type: ignore[assignment, misc]

try:
    from legacy_spikes.secondhand_publisher.publishers.daangn import (
        DaangnPublisher as LegacyDaangnPublisher,
    )
except ImportError:
    LegacyDaangnPublisher = None  # type: ignore[assignment, misc]

# ── 모델 ─────────────────────────────────────────────────────
try:
    from legacy_spikes.secondhand_publisher.core.models import (
        ListingPackage,
        Platform,
        ProductCondition,
        PublishResult as LegacyPublishResult,
        SellStrategy,
    )
except ImportError:
    ListingPackage = None  # type: ignore[assignment, misc]
    Platform = None  # type: ignore[assignment, misc]
    ProductCondition = None  # type: ignore[assignment, misc]
    LegacyPublishResult = None  # type: ignore[assignment, misc]
    SellStrategy = None  # type: ignore[assignment, misc]
