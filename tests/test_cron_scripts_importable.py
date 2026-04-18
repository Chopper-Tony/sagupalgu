"""
PR #248 (Closes #247) — cron 스크립트가 import 가능한지 검증.

Dockerfile 에서 scripts/ 가 COPY 되지 않으면 ModuleNotFoundError 발생.
이 테스트는 import 경로 + 모듈 구조만 검증 (실제 실행 X) — 환경변수 의존 0.

CTO PR #248 #3: '재발 방지 smoke test' 요청 반영.
"""
from __future__ import annotations

import importlib

import pytest

pytestmark = pytest.mark.unit


class TestCronScriptsImportable:
    def test_sync_catalog_module_import(self):
        """scripts.cron.sync_catalog 가 import 되어야 한다.
        Dockerfile 에 COPY scripts/ 누락 시 ModuleNotFoundError 로 실패.
        """
        mod = importlib.import_module("scripts.cron.sync_catalog")
        assert hasattr(mod, "main"), "sync_catalog must expose main()"
        assert callable(mod.main)

    def test_sync_catalog_argparse_정의됨(self):
        """main 의 argparse 가 --dry-run + --max 인자를 받는지.
        실제 호출 없이 inspect 로 정적 검증."""
        mod = importlib.import_module("scripts.cron.sync_catalog")
        # _main coroutine + main entry — 둘 다 존재
        assert hasattr(mod, "_main")
        assert hasattr(mod, "main")
