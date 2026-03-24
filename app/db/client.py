from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from supabase import Client

from app.core.config import settings

_supabase: Client | None = None


def get_supabase() -> Client:
    global _supabase
    if _supabase is None:
        from supabase import create_client  # lazy import — 미설치 환경에서 import 단계 통과
        _supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)
    return _supabase
