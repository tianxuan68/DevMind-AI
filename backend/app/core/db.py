"""数据库与缓存连接管理。

- MySQL：aiomysql 连接池，避免每次请求新建连接
- Redis：按业务拆多个 db：
  db 1 = 短信验证码
  db 2 = 用户问题缓存（解决缓存穿透/雪崩）
  db 3 = JWT 黑名单
"""
import aiomysql
from redis import asyncio as aioredis

from .config import settings


class Database:
    def __init__(self):
        self.mysql_pool = None
        self.redis_sms = None
        self.redis_question = None
        self.redis_token = None

    async def connect(self):
        """应用启动时初始化连接池。"""
        self.mysql_pool = await aiomysql.create_pool(
            host=settings.MYSQL_HOST,
            port=settings.MYSQL_PORT,
            user=settings.MYSQL_USER,
            password=settings.MYSQL_PASSWORD,
            db=settings.MYSQL_DATABASE,
            charset="utf8mb4",
            autocommit=True,
            minsize=settings.MYSQL_POOL_MINSIZE,
            maxsize=settings.MYSQL_POOL_SIZE,
            pool_recycle=3600,
        )

        password = settings.REDIS_PASSWORD or None
        self.redis_sms = aioredis.from_url(
            f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}/{settings.REDIS_SMS_DB}",
            password=password,
            decode_responses=True,
        )
        self.redis_question = aioredis.from_url(
            f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}/{settings.REDIS_QUESTION_DB}",
            password=password,
            decode_responses=True,
        )
        self.redis_token = aioredis.from_url(
            f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}/{settings.REDIS_TOKEN_DB}",
            password=password,
            decode_responses=True,
        )

    async def close(self):
        """应用关闭时释放连接池。"""
        if self.mysql_pool:
            self.mysql_pool.close()
            await self.mysql_pool.wait_closed()
        for redis_client in (self.redis_sms, self.redis_question, self.redis_token):
            if redis_client:
                await redis_client.aclose()

    async def fetch_one(self, sql: str, params: tuple = ()) -> dict | None:
        """查询单行。"""
        async with self.mysql_pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(sql, params)
                return await cur.fetchone()

    async def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
        """查询多行。"""
        async with self.mysql_pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(sql, params)
                return await cur.fetchall()

    async def execute(self, sql: str, params: tuple = ()) -> int:
        """执行写操作，返回受影响行数。"""
        async with self.mysql_pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(sql, params)
                return cur.rowcount

    async def execute_lastrowid(self, sql: str, params: tuple = ()) -> int:
        """执行插入并返回自增 ID。"""
        async with self.mysql_pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(sql, params)
                return cur.lastrowid


db = Database()
