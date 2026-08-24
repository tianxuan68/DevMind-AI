"""用户服务：短信验证码、注册、登录、用户信息。"""
import asyncio
import logging
import random
import secrets

from fastapi import HTTPException
from pymysql.err import IntegrityError

from backend.app.core.config import settings
from backend.app.core.db import db
from backend.app.core.security import hash_password, verify_password
from backend.app.services import sms_service

logger = logging.getLogger("devmind.user")

_SMS_CODE_PREFIX = "sms:code:"
_SMS_RATE_PREFIX = "sms:rate:"


async def send_sms_code(phone: str) -> dict:
    """发送手机验证码。"""
    rate_key = f"{_SMS_RATE_PREFIX}{phone}"
    if not await db.redis_sms.set(rate_key, "1", ex=settings.SMS_SEND_INTERVAL, nx=True):
        raise HTTPException(status_code=429, detail="验证码发送过于频繁，请稍后再试")

    code = str(random.randint(100000, 999999))
    code_key = f"{_SMS_CODE_PREFIX}{phone}"
    try:
        await sms_service.send_verification_code(phone, code)
    except Exception:
        await db.redis_sms.delete(rate_key)
        raise

    await db.redis_sms.set(code_key, code, ex=settings.SMS_CODE_TTL)
    logger.info("SMS code stored phone=%s***%s", phone[:3], phone[-4:])

    result = {
        "message": "验证码已发送",
        "expire_seconds": settings.SMS_CODE_TTL,
        "send_interval": settings.SMS_SEND_INTERVAL,
    }
    # 未启用真实短信时返回 debug_code，便于本地完成验证码登录联调
    if not settings.SPUG_SMS_ENABLED:
        result["debug_code"] = code
    return result


async def verify_sms_code(phone: str, code: str) -> None:
    """校验短信验证码，校验成功后删除，防止重复使用。"""
    key = f"{_SMS_CODE_PREFIX}{phone}"
    saved = await db.redis_sms.get(key)
    if not saved or saved != code:
        raise HTTPException(status_code=400, detail="验证码错误或已过期")
    await db.redis_sms.delete(key)


async def register_user(username: str, password: str, phone: str, sms_code: str, nickname: str | None = None, team: str = "default") -> dict:
    """用户注册。"""
    await verify_sms_code(phone, sms_code)

    # 用户名和手机号唯一性检查
    if await db.fetch_one("SELECT id FROM users WHERE username=%s", (username,)):
        raise HTTPException(status_code=400, detail="用户名已存在")
    if await db.fetch_one("SELECT id FROM users WHERE phone=%s", (phone,)):
        raise HTTPException(status_code=400, detail="手机号已注册")

    try:
        user_id = await db.execute_lastrowid(
            """INSERT INTO users (username, password_hash, nickname, phone, team, security_level)
               VALUES (%s, %s, %s, %s, %s, 'team')""",
            (username, await asyncio.to_thread(hash_password, password), nickname or username, phone, team),
        )
    except IntegrityError:
        # 并发注册时，两个请求可能同时通过前面的唯一性检查，这里兜底
        raise HTTPException(status_code=400, detail="用户名或手机号已存在")
    return {
        "id": user_id,
        "username": username,
        "nickname": nickname or username,
        "phone": phone,
        "team": team,
        "security_level": "team",
    }


async def login_by_account(account: str, password: str) -> dict:
    """账号密码登录，account 支持用户名或手机号。"""
    user = await db.fetch_one(
        "SELECT * FROM users WHERE username=%s OR phone=%s LIMIT 1",
        (account, account),
    )
    if not user or not await asyncio.to_thread(verify_password, password, user["password_hash"]):
        raise HTTPException(status_code=400, detail="用户名或密码错误")
    if not user["is_active"]:
        raise HTTPException(status_code=403, detail="账号已被禁用")

    return _public_user(user)


async def login_by_sms(phone: str, sms_code: str) -> dict:
    """手机号验证码登录；未注册手机号自动创建账号。"""
    await verify_sms_code(phone, sms_code)
    user = await db.fetch_one("SELECT * FROM users WHERE phone=%s LIMIT 1", (phone,))
    if not user:
        user = await _auto_register_by_phone(phone)
    if not user["is_active"]:
        raise HTTPException(status_code=403, detail="账号已被禁用")

    return _public_user(user)


async def _auto_register_by_phone(phone: str) -> dict:
    """验证码登录时，为未注册手机号自动建号。"""
    username = f"u{phone}"
    nickname = f"用户{phone[-4:]}"
    password_hash = await asyncio.to_thread(hash_password, secrets.token_urlsafe(16))
    try:
        user_id = await db.execute_lastrowid(
            """INSERT INTO users (username, password_hash, nickname, phone, team, security_level)
               VALUES (%s, %s, %s, %s, 'default', 'team')""",
            (username, password_hash, nickname, phone),
        )
    except IntegrityError:
        user = await db.fetch_one("SELECT * FROM users WHERE phone=%s LIMIT 1", (phone,))
        if user:
            return user
        raise HTTPException(status_code=400, detail="自动注册失败，请稍后重试")

    logger.info("Auto registered user phone=%s***%s user_id=%s", phone[:3], phone[-4:], user_id)
    user = await db.fetch_one("SELECT * FROM users WHERE id=%s LIMIT 1", (user_id,))
    if not user:
        raise HTTPException(status_code=500, detail="自动注册失败，请稍后重试")
    return user


def _public_user(user: dict) -> dict:
    """只返回可暴露给前端的用户信息。"""
    return {
        "id": user["id"],
        "username": user["username"],
        "nickname": user.get("nickname") or user["username"],
        "phone": user.get("phone"),
        "team": user.get("team"),
        "security_level": user.get("security_level"),
    }
