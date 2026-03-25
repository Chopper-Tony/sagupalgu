"""API 타입 동기화 검증 — 백엔드 스키마와 프론트엔드 타입의 drift 감지."""
import pytest


class TestSessionStatusSync:
    """백엔드 SessionStatus와 프론트엔드 타입의 상태 집합이 일치하는지."""

    @pytest.mark.unit
    def test_backend_statuses_match_generated(self):
        from app.domain.session_status import ALLOWED_TRANSITIONS
        from pathlib import Path

        generated = Path("frontend/src/types/api-generated.ts").read_text(encoding="utf-8")
        for status in ALLOWED_TRANSITIONS:
            assert f'"{status}"' in generated, (
                f"백엔드 상태 '{status}'가 api-generated.ts에 없습니다. "
                "python scripts/generate_api_types.py 실행 필요."
            )

    @pytest.mark.unit
    def test_frontend_manual_statuses_match_backend(self):
        """수동 관리 session.ts의 SessionStatus가 백엔드와 일치하는지."""
        from app.domain.session_status import ALLOWED_TRANSITIONS
        from pathlib import Path

        ts_content = Path("frontend/src/types/session.ts").read_text(encoding="utf-8")
        for status in ALLOWED_TRANSITIONS:
            assert f'"{status}"' in ts_content, (
                f"백엔드 상태 '{status}'가 frontend/src/types/session.ts에 없습니다."
            )


class TestResponseFieldSync:
    """백엔드 응답의 평탄화 필드가 프론트엔드 타입에 존재하는지."""

    FRONTEND_REQUIRED = {
        "session_id", "status", "needs_user_input",
        "clarification_prompt", "product_candidates", "confirmed_product",
        "canonical_listing", "market_context", "platform_results",
        "optimization_suggestion", "image_urls", "selected_platforms",
    }

    @pytest.mark.unit
    def test_generated_has_all_frontend_fields(self):
        from pathlib import Path

        generated = Path("frontend/src/types/api-generated.ts").read_text(encoding="utf-8")
        for field in self.FRONTEND_REQUIRED:
            assert field in generated, (
                f"필드 '{field}'가 api-generated.ts에 없습니다."
            )

    @pytest.mark.unit
    def test_manual_types_have_all_frontend_fields(self):
        from pathlib import Path

        ts_content = Path("frontend/src/types/session.ts").read_text(encoding="utf-8")
        for field in self.FRONTEND_REQUIRED:
            assert field in ts_content, (
                f"필드 '{field}'가 session.ts에 없습니다."
            )


class TestGeneratedFileExists:
    @pytest.mark.unit
    def test_api_generated_ts_exists(self):
        from pathlib import Path
        assert Path("frontend/src/types/api-generated.ts").exists(), (
            "api-generated.ts 파일이 없습니다. python scripts/generate_api_types.py 실행 필요."
        )
