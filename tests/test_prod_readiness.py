"""
M104+M105: Prod 점검 + Smoke Test 테스트
"""
import pytest
from unittest.mock import MagicMock, patch

pytestmark = pytest.mark.unit


class TestProdReadiness:

    def test_wildcard_cors_감지(self):
        from scripts.check_prod_readiness import check_prod_readiness
        mock_settings = MagicMock()
        mock_settings.allowed_origins = "*"
        mock_settings.environment = "prod"
        mock_settings.debug = False
        mock_settings.secret_encryption_key = "real-key-32-characters-long!!"
        mock_settings.openai_api_key = "sk-test"
        mock_settings.gemini_api_key = None
        mock_settings.supabase_jwt_secret = "jwt-secret"
        mock_settings.bunjang_username = "user"
        mock_settings.joongna_username = "user"

        with patch("app.core.config.get_settings", return_value=mock_settings):
            issues = check_prod_readiness("prod")

        cors_issues = [i for i in issues if i["check"] == "cors_origins"]
        assert len(cors_issues) == 1
        assert cors_issues[0]["level"] == "error"

    def test_debug_mode_감지(self):
        from scripts.check_prod_readiness import check_prod_readiness
        mock_settings = MagicMock()
        mock_settings.allowed_origins = "https://example.com"
        mock_settings.environment = "prod"
        mock_settings.debug = True
        mock_settings.secret_encryption_key = "real-key"
        mock_settings.openai_api_key = "sk-test"
        mock_settings.gemini_api_key = None
        mock_settings.supabase_jwt_secret = "jwt"
        mock_settings.bunjang_username = "user"
        mock_settings.joongna_username = "user"

        with patch("app.core.config.get_settings", return_value=mock_settings):
            issues = check_prod_readiness("prod")

        debug_issues = [i for i in issues if i["check"] == "debug_mode"]
        assert len(debug_issues) == 1
        assert debug_issues[0]["level"] == "error"

    def test_정상_설정_통과(self):
        from scripts.check_prod_readiness import check_prod_readiness
        mock_settings = MagicMock()
        mock_settings.allowed_origins = "https://sagupalgu.com"
        mock_settings.environment = "prod"
        mock_settings.debug = False
        mock_settings.secret_encryption_key = "real-secret-key-for-production!!"
        mock_settings.openai_api_key = "sk-real"
        mock_settings.gemini_api_key = None
        mock_settings.supabase_jwt_secret = "real-jwt-secret"
        mock_settings.bunjang_username = "user"
        mock_settings.joongna_username = "user"

        with patch("app.core.config.get_settings", return_value=mock_settings):
            issues = check_prod_readiness("prod")

        errors = [i for i in issues if i["level"] == "error"]
        assert len(errors) == 0

    def test_llm_키_없으면_에러(self):
        from scripts.check_prod_readiness import check_prod_readiness
        mock_settings = MagicMock()
        mock_settings.allowed_origins = "https://sagupalgu.com"
        mock_settings.environment = "prod"
        mock_settings.debug = False
        mock_settings.secret_encryption_key = "real-key"
        mock_settings.openai_api_key = None
        mock_settings.gemini_api_key = None
        mock_settings.upstage_api_key = None
        mock_settings.supabase_jwt_secret = "jwt"
        mock_settings.bunjang_username = "user"
        mock_settings.joongna_username = "user"

        with patch("app.core.config.get_settings", return_value=mock_settings):
            issues = check_prod_readiness("prod")

        llm_issues = [i for i in issues if i["check"] == "llm_api_key"]
        assert len(llm_issues) == 1

    def test_placeholder_키_감지(self):
        from scripts.check_prod_readiness import check_prod_readiness
        mock_settings = MagicMock()
        mock_settings.allowed_origins = "https://sagupalgu.com"
        mock_settings.environment = "prod"
        mock_settings.debug = False
        mock_settings.secret_encryption_key = "placeholder-encryption-key-32ch"
        mock_settings.openai_api_key = "sk-real"
        mock_settings.gemini_api_key = None
        mock_settings.supabase_jwt_secret = "jwt"
        mock_settings.bunjang_username = "user"
        mock_settings.joongna_username = "user"

        with patch("app.core.config.get_settings", return_value=mock_settings):
            issues = check_prod_readiness("prod")

        key_issues = [i for i in issues if i["check"] == "encryption_key"]
        assert len(key_issues) == 1


class TestSmokeTestScript:

    def test_run_smoke_tests_함수_존재(self):
        from scripts.smoke_test import run_smoke_tests
        assert callable(run_smoke_tests)

    def test_check_prod_readiness_함수_존재(self):
        from scripts.check_prod_readiness import check_prod_readiness
        assert callable(check_prod_readiness)
