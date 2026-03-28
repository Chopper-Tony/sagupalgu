import json
from functools import lru_cache
from typing import Any

from cryptography.fernet import Fernet


@lru_cache
def _get_fernet() -> Fernet:
    """Fernet 인스턴스를 lazy 생성 (import 시점이 아닌 최초 호출 시)."""
    from app.core.config import get_settings
    return Fernet(get_settings().secret_encryption_key.encode())


def encrypt_payload(data: dict[str, Any]) -> str:
    payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
    return _get_fernet().encrypt(payload).decode("utf-8")


def decrypt_payload(token: str) -> dict[str, Any]:
    decrypted = _get_fernet().decrypt(token.encode("utf-8"))
    return json.loads(decrypted.decode("utf-8"))
