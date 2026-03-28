"""M85: 전달물 위생 스크립트 테스트."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# 프로젝트 루트
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# scripts 모듈 import
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
from build_archive import _parse_ignore_file, _should_exclude, collect_files


# ──────────────────────────────────────────
# .archiveignore 패턴 검증
# ──────────────────────────────────────────

@pytest.mark.unit
class TestArchiveIgnorePatterns:
    """archiveignore 파일 내용 검증."""

    def _load_patterns(self) -> list[str]:
        return _parse_ignore_file(PROJECT_ROOT / ".archiveignore")

    def test_archive_excludes_env(self):
        """.archiveignore에 .env 패턴이 존재해야 한다."""
        patterns = self._load_patterns()
        env_patterns = [p for p in patterns if ".env" in p and not p.startswith("!")]
        assert len(env_patterns) >= 1, ".env 제외 패턴이 없음"

    def test_archive_excludes_pycache(self):
        """__pycache__ 제외 패턴 존재."""
        patterns = self._load_patterns()
        assert any("__pycache__" in p for p in patterns)

    def test_archive_excludes_git(self):
        """.git/ 제외 패턴 존재."""
        patterns = self._load_patterns()
        assert any(".git" == p.rstrip("/") for p in patterns)

    def test_archive_excludes_node_modules(self):
        """frontend/node_modules 제외 패턴 존재."""
        patterns = self._load_patterns()
        assert any("node_modules" in p for p in patterns)

    def test_archive_excludes_venv(self):
        """가상환경 제외 패턴 존재."""
        patterns = self._load_patterns()
        assert any("venv" in p.lower() for p in patterns)

    def test_archive_preserves_env_example(self):
        """.env.example은 네거티브 패턴으로 보존."""
        patterns = self._load_patterns()
        assert any(p == "!.env.example" for p in patterns)


# ──────────────────────────────────────────
# 필수 파일 포함 검증
# ──────────────────────────────────────────

@pytest.mark.unit
class TestArchiveIncludesEssentials:
    """archive에 필수 파일이 포함되는지 검증."""

    def _files(self) -> list[str]:
        return collect_files(PROJECT_ROOT)

    def test_archive_includes_essential_files(self):
        """app/main.py, requirements.txt가 포함되어야 한다."""
        files = self._files()
        assert "app/main.py" in files, "app/main.py 누락"
        assert "requirements.txt" in files, "requirements.txt 누락"

    def test_archive_includes_readme(self):
        """README.md가 포함되어야 한다."""
        files = self._files()
        assert "README.md" in files, "README.md 누락"

    def test_archive_includes_env_example(self):
        """.env.example이 포함되어야 한다."""
        files = self._files()
        assert ".env.example" in files, ".env.example 누락"

    def test_archive_includes_tests(self):
        """테스트 파일이 포함되어야 한다."""
        files = self._files()
        test_files = [f for f in files if f.startswith("tests/") and f.endswith(".py")]
        assert len(test_files) > 0, "테스트 파일 누락"


# ──────────────────────────────────────────
# 제외 로직 단위 테스트
# ──────────────────────────────────────────

@pytest.mark.unit
class TestShouldExclude:
    """_should_exclude 함수 단위 테스트."""

    def test_exclude_env(self):
        patterns = [".env", ".env.*", "!.env.example"]
        assert _should_exclude(".env", patterns) is True

    def test_exclude_env_local(self):
        patterns = [".env", ".env.*", "!.env.example"]
        assert _should_exclude(".env.local", patterns) is True

    def test_include_env_example(self):
        """네거티브 패턴으로 .env.example은 포함."""
        patterns = [".env", ".env.*", "!.env.example"]
        assert _should_exclude(".env.example", patterns) is False

    def test_exclude_pycache(self):
        patterns = ["__pycache__/"]
        assert _should_exclude("app/__pycache__/foo.pyc", patterns) is True

    def test_exclude_git_dir(self):
        patterns = [".git/"]
        assert _should_exclude(".git/config", patterns) is True

    def test_include_normal_file(self):
        patterns = [".env", "__pycache__/", ".git/"]
        assert _should_exclude("app/main.py", patterns) is False

    def test_exclude_sqlite(self):
        patterns = ["*.sqlite3", "*.db"]
        assert _should_exclude("data/local.sqlite3", patterns) is True
        assert _should_exclude("data/app.db", patterns) is True

    def test_exclude_claude_dir(self):
        patterns = [".claude/"]
        assert _should_exclude(".claude/rules/coding-rules.md", patterns) is True
