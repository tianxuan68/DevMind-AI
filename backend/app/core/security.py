"""安全模块：密码哈希、JWT 签发/校验、当前登录用户依赖。"""
import hashlib
import hmac
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import settings
from .db import db

bearer_scheme = HTTPBearer(auto_error=False)

# 密码格式：pbkdf2_sha256$迭代次数$盐$哈希
_PBKDF2_ITERATIONS = 100_000


def hash_password(password: str) -> str:
    """生成密码哈希。"""
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${_PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, password_hash: str) -> bool:
    """校验密码。"""
    try:
        algorithm, iterations, salt_hex, hash_hex = password_hash.split("$")
        if algorithm != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            bytes.fromhex(salt_hex),
            int(iterations),
        )
        return hmac.compare_digest(digest.hex(), hash_hex)
    except Exception:
        return False


def create_access_token(user: dict) -> str:
    """签发 JWT。"""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user["id"]),
        "username": user["username"],
        "nickname": user.get("nickname"),
        "name": user.get("nickname") or user.get("username") or "",
        "phone": user.get("phone"),
        "team": user.get("team"),
        "security_level": user.get("security_level", "team"),
        "jti": uuid.uuid4().hex,
        "iat": now,
        "exp": now + timedelta(hours=settings.JWT_EXPIRE_HOURS),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    """解析 JWT，失败统一抛 401。"""
    try:
        return jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
    except jwt.PyJWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="无效或过期的登录凭证")


async def is_token_blacklisted(jti: str) -> bool:
    """判断 JWT 是否已退出/拉黑。"""
    return bool(await db.redis_token.exists(f"jwt:blacklist:{jti}"))


async def blacklist_token(payload: dict) -> None:
    """将 JWT jti 加入黑名单，保留到过期时间。"""
    exp = payload.get("exp")
    if not exp:
        return
    ttl = int(exp) - int(datetime.now(timezone.utc).timestamp())
    if ttl > 0:
        await db.redis_token.set(f"jwt:blacklist:{payload['jti']}", "1", ex=int(ttl))


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> dict:
    """FastAPI 依赖：从 Authorization 中解析当前登录用户。"""
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="请先登录")

    payload = decode_token(credentials.credentials)
    if await is_token_blacklisted(payload.get("jti", "")):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="登录已失效，请重新登录")

    return {
        "id": int(payload["sub"]),
        "username": payload.get("username"),
        "nickname": payload.get("nickname"),
        "phone": payload.get("phone"),
        "team": payload.get("team"),
        "security_level": payload.get("security_level"),
        "jti": payload.get("jti"),
        "exp": payload.get("exp"),
    }
