"""Encrypt model credentials with a persistent key separate from the database."""
from pathlib import Path
from cryptography.fernet import Fernet, InvalidToken
from app.core.config import settings


def _cipher() -> Fernet:
    key = settings.MODEL_ENCRYPTION_KEY
    if not key:
        path = Path(settings.MODEL_ENCRYPTION_KEY_FILE)
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            try:
                with path.open("xb") as file:
                    file.write(Fernet.generate_key())
            except FileExistsError:
                pass
        key = path.read_bytes()
    return Fernet(key)


def encrypt_api_key(value: str) -> str:
    return _cipher().encrypt(value.encode()).decode() if value else ""


def decrypt_api_key(value: str) -> str:
    if not value:
        return ""
    try:
        return _cipher().decrypt(value.encode()).decode()
    except InvalidToken as exc:
        raise ValueError("模型密钥无法解密，请编辑模型并重新填写密钥") from exc
