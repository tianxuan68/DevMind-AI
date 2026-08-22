"""用户问题缓存模块。

Redis 单独使用 db 2 缓存用户查询过的问题答案。

设计：
- 命中缓存：直接返回，不打 MySQL
- 未命中且 MySQL 有结果：写入随机 TTL，避免缓存雪崩
- MySQL 也没有结果：写入空值标记 + 短随机 TTL，避免缓存穿透打爆 MySQL
- 并发重建：用 Redis 单机锁 + 指数退避，避免热点问题同时打到 MySQL
"""
import asyncio
import hashlib
import json
import random

from .config import settings
from .db import db

EMPTY_MARKER = "__EMPTY__"
_LOCK_PREFIX = "qa:lock:"
_CACHE_PREFIX = "qa:q:"


def _cache_key(question: str) -> str:
    md5 = hashlib.md5(question.strip().encode("utf-8")).hexdigest()
    return f"{_CACHE_PREFIX}{md5}"


def _lock_key(question: str) -> str:
    md5 = hashlib.md5(question.strip().encode("utf-8")).hexdigest()
    return f"{_LOCK_PREFIX}{md5}"


def _random_ttl(base_ttl: int) -> int:
    """在基础 TTL 上增加随机抖动，防止同一时间大量 key 一起过期。"""
    return base_ttl + random.randint(0, 120)


async def get_question_cache(question: str):
    """返回 (是否存在缓存, 缓存值)。"""
    raw = await db.redis_question.get(_cache_key(question))
    if raw is None:
        return False, None
    if raw == EMPTY_MARKER:
        return True, None
    try:
        return True, json.loads(raw)
    except json.JSONDecodeError:
        # 异常数据按空处理，避免影响主流程
        await db.redis_question.delete(_cache_key(question))
        return False, None


async def set_question_cache(question: str, data: dict) -> None:
    """写入正常答案缓存，随机 TTL。"""
    await db.redis_question.set(
        _cache_key(question),
        json.dumps(data, ensure_ascii=False),
        ex=_random_ttl(settings.QUESTION_CACHE_TTL),
    )


async def set_question_empty(question: str) -> None:
    """写入空值缓存，短随机 TTL，解决缓存穿透。"""
    await db.redis_question.set(
        _cache_key(question),
        EMPTY_MARKER,
        ex=random.randint(1, max(1, settings.QUESTION_EMPTY_TTL)),
    )


async def acquire_question_lock(question: str) -> bool:
    """获取单机 Redis 锁（非分布式架构）。"""
    return bool(
        await db.redis_question.set(
            _lock_key(question),
            "1",
            ex=settings.CACHE_LOCK_TIMEOUT,
            nx=True,
        )
    )


async def release_question_lock(question: str) -> None:
    """释放 Redis 锁。"""
    await db.redis_question.delete(_lock_key(question))


async def wait_and_get_cache(question: str, max_retry: int = 3) -> tuple[bool, dict | None]:
    """获取锁失败时，指数退避等待其他线程写入缓存。

    等待间隔：50ms -> 100ms -> 200ms -> 400ms
    """
    for i in range(max_retry):
        await asyncio.sleep(0.05 * (2**i))
        exists, data = await get_question_cache(question)
        if exists:
            return True, data
    return False, None
