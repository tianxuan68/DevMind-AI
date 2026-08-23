"""Redis 客户端与会话缓存（T8）。

职责：
- 通用 JSON 存取（set_data / get_data）
- FAQ 答案热缓存（get_answer / set_answer）
- 会话上下文缓存（set_session / get_session）
- 转人工工单队列（push_ticket / pop_ticket）

Redis 不可用时自动降级为进程内内存缓存（开发/联调期契约可测），
并记录警告；生产环境必须保证 Redis 可用。

参考基线：Itcast_qa_system/mysql_qa/cache/redis_client.py
"""
import json
import logging
import socket
import threading

import redis

from base.config import Config

logger = logging.getLogger("mysql_qa.cache.redis_client")


class _MemoryCache:
    """Redis 不可用时的内存降级实现，接口与 Redis 命令子集一致。"""

    def __init__(self):
        self._data: dict = {}
        self._lock = threading.Lock()

    def set(self, key, value, ex=None):
        with self._lock:
            self._data[key] = value

    def get(self, key):
        with self._lock:
            return self._data.get(key)

    def incr(self, key):
        with self._lock:
            self._data[key] = int(self._data.get(key, 0)) + 1
            return self._data[key]

    def rpush(self, key, value):
        with self._lock:
            self._data.setdefault(key, []).append(value)

    def lpop(self, key):
        with self._lock:
            queue = self._data.get(key)
            return queue.pop(0) if queue else None

    def ping(self):
        return True


def _probe_redis(host: str, port: int, timeout: float = 2.0) -> bool:
    """TCP 预检：redis-py 的连接失败路径在 Windows 上可能耗时数十秒，
    先快速探测避免启动/测试卡顿。"""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


class RedisClient:
    def __init__(self, config: Config | None = None):
        self.config = config or Config()
        if not _probe_redis(self.config.REDIS_HOST, self.config.REDIS_PORT):
            logger.warning(
                "Redis 不可达 (%s:%s)，降级为进程内内存缓存",
                self.config.REDIS_HOST,
                self.config.REDIS_PORT,
            )
            self.client = _MemoryCache()
            return
        try:
            self.client = redis.StrictRedis(
                host=self.config.REDIS_HOST,
                port=self.config.REDIS_PORT,
                password=self.config.REDIS_PASSWORD,
                db=self.config.REDIS_DB,
                decode_responses=True,
                socket_connect_timeout=3,
            )
            self.client.ping()
            logger.info("Redis 连接成功 (%s:%s)", self.config.REDIS_HOST, self.config.REDIS_PORT)
        except redis.RedisError as e:
            logger.warning("Redis 连接失败，降级为进程内内存缓存（%s）", e)
            self.client = _MemoryCache()

    # ---- 通用 JSON 存取 ----

    def set_data(self, key: str, value) -> None:
        try:
            self.client.set(key, json.dumps(value, ensure_ascii=False))
        except redis.RedisError as e:
            logger.error("Redis 存储失败 key=%s: %s", key, e)

    def get_data(self, key: str):
        try:
            data = self.client.get(key)
            return json.loads(data) if data else None
        except redis.RedisError as e:
            logger.error("Redis 获取失败 key=%s: %s", key, e)
            return None

    # ---- FAQ 答案热缓存 ----

    def get_answer(self, query: str) -> str | None:
        try:
            answer = self.client.get(f"answer:{query}")
            if answer:
                logger.info("从 Redis 命中答案缓存: %s", query)
            return answer
        except redis.RedisError as e:
            logger.error("Redis 答案缓存查询失败: %s", e)
            return None

    def set_answer(self, query: str, answer: str) -> None:
        try:
            self.client.set(f"answer:{query}", answer, ex=self.config.ANSWER_CACHE_TTL)
        except redis.RedisError as e:
            logger.error("Redis 答案缓存写入失败: %s", e)

    # ---- 会话上下文缓存 ----

    def set_session(self, session_id: str, history: list) -> None:
        """缓存会话最近 N 轮问答历史。"""
        self.set_data(f"session:{session_id}", history)

    def get_session(self, session_id: str) -> list:
        """读取会话历史，无则返回空列表。"""
        return self.get_data(f"session:{session_id}") or []

    # ---- 转人工工单队列 ----

    def push_ticket(self, ticket: dict) -> None:
        """工单入队（转人工队列，供人工处理侧消费）。"""
        try:
            self.client.rpush(self.config.TICKET_QUEUE_KEY, json.dumps(ticket, ensure_ascii=False))
            logger.info("工单入队: %s", ticket.get("ticket_no"))
        except redis.RedisError as e:
            logger.error("工单入队失败: %s", e)

    def pop_ticket(self) -> dict | None:
        """从队列取出一条待处理工单。"""
        try:
            data = self.client.lpop(self.config.TICKET_QUEUE_KEY)
            return json.loads(data) if data else None
        except redis.RedisError as e:
            logger.error("工单出队失败: %s", e)
            return None


def main():
    """冒烟自测：python -m mysql_qa.cache.redis_client"""
    logging.basicConfig(level=logging.INFO)
    client = RedisClient()
    client.set_data("user:1", {"name": "Alice"})
    print(client.get_data("user:1"))
    client.set_answer("测试问题", "测试答案")
    print(client.get_answer("测试问题"))
    client.push_ticket({"ticket_no": "TK0001"})
    print(client.pop_ticket())


if __name__ == "__main__":
    main()
