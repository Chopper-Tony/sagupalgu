"""
M94: Publish Spine 정리 테스트

각 publisher의 build_account_context classmethod와 registry 위임을 검증한다.
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock

pytestmark = pytest.mark.unit


class TestPublisherAccountContext:

    def _mock_settings(self, **overrides):
        s = MagicMock()
        s.joongna_username = overrides.get("joongna_username", "user")
        s.joongna_password = overrides.get("joongna_password", "pass")
        s.bunjang_username = overrides.get("bunjang_username", "user")
        s.bunjang_password = overrides.get("bunjang_password", "pass")
        s.daangn_device_id = overrides.get("daangn_device_id", "device-123")
        return s

    def test_joongna_account_context(self):
        from app.publishers.joongna_publisher import JoongnaPublisher
        ctx = JoongnaPublisher.build_account_context(self._mock_settings())
        assert ctx.platform == "joongna"
        assert ctx.auth_type == "id_password"
        assert ctx.secret_payload["username"] == "user"

    def test_joongna_no_credentials_raises(self):
        from app.publishers.joongna_publisher import JoongnaPublisher
        with pytest.raises(ValueError, match="Joongna"):
            JoongnaPublisher.build_account_context(
                self._mock_settings(joongna_username="", joongna_password=""),
            )

    def test_bunjang_account_context(self):
        from app.publishers.bunjang_publisher import BunjangPublisher
        ctx = BunjangPublisher.build_account_context(self._mock_settings())
        assert ctx.platform == "bunjang"
        assert ctx.auth_type == "username_password"

    def test_daangn_account_context(self):
        from app.publishers.daangn_publisher import DaangnPublisher
        ctx = DaangnPublisher.build_account_context(self._mock_settings())
        assert ctx.platform == "daangn"
        assert ctx.auth_type == "device"
        assert ctx.secret_payload["device_id"] == "device-123"

    def test_publish_service_delegates_to_publisher(self):
        """PublishService.build_account_context가 publisher classmethod로 위임"""
        from app.services.publish_service import PublishService
        from unittest.mock import patch

        svc = PublishService()
        mock_settings = self._mock_settings()

        with patch("app.services.publish_service.settings", mock_settings):
            ctx = svc.build_account_context("bunjang")
        assert ctx.platform == "bunjang"

    def test_unsupported_platform_raises(self):
        from app.services.publish_service import PublishService
        svc = PublishService()
        with pytest.raises(ValueError, match="Unsupported"):
            svc.build_account_context("unknown_platform")

    def test_registry_covers_all_publishers(self):
        """PUBLISHER_REGISTRY가 3개 플랫폼을 모두 포함"""
        from app.services.publish_service import PublishService
        assert set(PublishService.PUBLISHER_REGISTRY.keys()) == {"joongna", "bunjang", "daangn"}
