"""
安全模块 - JWT 认证 + 密码哈希

注：bcrypt 5.x 已不兼容 passlib 的版本检测，这里直接用 bcrypt 原生 API，
同时在 hash 和 verify 里做 bcrypt 4.x+ 的 72 字节限制兼容。
"""
from datetime import datetime, timedelta, timezone
from typing import Optional
import jwt as pyjwt
from jwt import PyJWTError
import bcrypt as _bcrypt

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger()

BCRYPT_MAX_BYTES = 72


def hash_password(password: str) -> str:
    """哈希密码（bcrypt）"""
    pw_bytes = password.encode("utf-8")
    if len(pw_bytes) > BCRYPT_MAX_BYTES:
        pw_bytes = pw_bytes[:BCRYPT_MAX_BYTES]
    hashed = _bcrypt.hashpw(pw_bytes, _bcrypt.gensalt())
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """验证密码"""
    try:
        pw_bytes = plain_password.encode("utf-8")
        if len(pw_bytes) > BCRYPT_MAX_BYTES:
            pw_bytes = pw_bytes[:BCRYPT_MAX_BYTES]
        return _bcrypt.checkpw(pw_bytes, hashed_password.encode("utf-8"))
    except ValueError as e:
        logger.warning(f"密码验证失败: {e}")
        return False
    except Exception as e:
        logger.warning(f"密码验证异常: {e}")
        return False


def create_access_token(
    data: dict,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """创建 JWT Token"""
    to_encode = data.copy()
    if "sub" in to_encode and not isinstance(to_encode["sub"], str):
        to_encode["sub"] = str(to_encode["sub"])
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire, "iat": datetime.now(timezone.utc)})
    token = pyjwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return token


def decode_access_token(token: str) -> Optional[dict]:
    """解码 JWT Token"""
    try:
        payload = pyjwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
        return payload
    except PyJWTError as e:
        logger.warning(f"Token 解码失败: {e}")
        return None
