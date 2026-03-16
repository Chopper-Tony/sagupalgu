import json
from typing import Any
from cryptography.fernet import Fernet
from app.core.config import settings

fernet = Fernet(settings.secret_encryption_key.encode())

def encrypt_payload(data: dict[str, Any]) -> str:
    payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
    return fernet.encrypt(payload).decode("utf-8")

def decrypt_payload(token: str) -> dict[str, Any]:
    decrypted = fernet.decrypt(token.encode("utf-8"))
    return json.loads(decrypted.decode("utf-8"))
