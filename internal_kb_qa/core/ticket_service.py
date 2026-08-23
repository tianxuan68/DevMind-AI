"""T8 转人工与工单联动 + 用户反馈落库。

职责：
- 工单：MySQL 落库（tickets 表）+ Redis 转人工队列 + 外部工单系统 API 同步；
- 反馈：点赞点踩/评论落库（feedback 表），need_human=true 时创建工单并返回
  ticket_id；
- 降级：MySQL 不可用时仅写 Redis 队列并记录错误，服务不中断（契约可测）。

说明：工单/反馈表 CRUD 目前自包含（pymysql 直连），T5 的 MySQLClient 交付后
可切换为统一数据访问层，接口不变。

验收标准：低置信度必生成工单、工单系统对接成功率、反馈落库完整率、工单状态流转。
"""
import json
import logging
import time
import urllib.error
import urllib.request

import pymysql

from base.config import Config
from mysql_qa.cache.redis_client import RedisClient

logger = logging.getLogger("internal_kb_qa.core.ticket_service")

# 工单状态流转：pending -> in_progress -> resolved / closed
TICKET_STATUS = ("pending", "in_progress", "resolved", "closed")

_CREATE_TABLES = """
CREATE TABLE IF NOT EXISTS tickets (
    id INT AUTO_INCREMENT PRIMARY KEY,
    ticket_no VARCHAR(40) NOT NULL UNIQUE,
    session_id VARCHAR(36) NOT NULL,
    query TEXT NOT NULL,
    user_id VARCHAR(64) NOT NULL,
    team VARCHAR(32) NOT NULL,
    reason VARCHAR(32) NOT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'pending',
    external_id VARCHAR(64) DEFAULT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_session (session_id),
    INDEX idx_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS feedback (
    id INT AUTO_INCREMENT PRIMARY KEY,
    session_id VARCHAR(36) NOT NULL,
    query TEXT NOT NULL,
    user_id VARCHAR(64) NOT NULL,
    rating TINYINT NOT NULL,
    comment TEXT DEFAULT NULL,
    need_human TINYINT(1) NOT NULL DEFAULT 0,
    ticket_no VARCHAR(40) DEFAULT NULL,
    kb_status VARCHAR(16) NOT NULL DEFAULT 'open',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_session (session_id),
    INDEX idx_kb_status (kb_status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""


class TicketService:
    """工单创建/同步与反馈落库。"""

    def __init__(self, config: Config | None = None, redis_client: RedisClient | None = None):
        self.config = config or Config()
        self.redis = redis_client or RedisClient(self.config)
        self.db = self._connect_mysql()
        if self.db:
            self._init_tables()
        else:
            logger.warning("MySQL 不可用，工单/反馈仅写 Redis 队列（降级模式）")

    # ---- 存储层 ----

    def _connect_mysql(self):
        try:
            conn = pymysql.connect(
                host=self.config.MYSQL_HOST,
                user=self.config.MYSQL_USER,
                password=self.config.MYSQL_PASSWORD,
                database=self.config.MYSQL_DATABASE,
                charset="utf8mb4",
                cursorclass=pymysql.cursors.DictCursor,
                connect_timeout=3,
            )
            logger.info("工单服务 MySQL 连接成功")
            return conn
        except pymysql.MySQLError as e:
            logger.error("工单服务 MySQL 连接失败: %s", e)
            return None

    def _init_tables(self) -> None:
        try:
            with self.db.cursor() as cur:
                for statement in _CREATE_TABLES.split(";"):
                    if statement.strip():
                        cur.execute(statement)
            self.db.commit()
            logger.info("tickets / feedback 表初始化完成")
        except pymysql.MySQLError as e:
            logger.error("工单表初始化失败: %s", e)
            self.db.close()
            self.db = None

    def _next_ticket_no(self) -> str:
        seq = self.redis.client.incr("ticket:seq")
        return f"TK{time.strftime('%Y%m%d')}{seq:05d}"

    # ---- 工单 ----

    def create_ticket(
        self,
        session_id: str,
        query: str,
        user_id: str,
        team: str,
        reason: str = "low_confidence",
    ) -> dict:
        """创建工单：落库（可用时）+ 入队 + 外部同步；返回工单信息。"""
        ticket = {
            "ticket_no": self._next_ticket_no(),
            "session_id": session_id,
            "query": query,
            "user_id": user_id,
            "team": team,
            "reason": reason,
            "status": "pending",
            "external_id": None,
        }
        if self.db:
            try:
                with self.db.cursor() as cur:
                    cur.execute(
                        """INSERT INTO tickets
                           (ticket_no, session_id, query, user_id, team, reason, status)
                           VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                        (ticket["ticket_no"], session_id, query, user_id, team, reason, "pending"),
                    )
                self.db.commit()
            except pymysql.MySQLError as e:
                logger.error("工单落库失败: %s", e)
                self.db.rollback()
        self.redis.push_ticket(ticket)
        if self.config.TICKET_EXTERNAL_ENABLED:
            ticket["external_id"] = self._sync_external(ticket)
        logger.info(
            "工单创建: %s (reason=%s, session=%s)", ticket["ticket_no"], reason, session_id
        )
        return ticket

    def _sync_external(self, ticket: dict) -> str | None:
        """同步外部工单系统；失败返回 None 并记录错误（不阻塞主流程）。"""
        if not self.config.TICKET_EXTERNAL_API_URL:
            logger.warning("external_enabled=true 但未配置 external_api_url，跳过外部同步")
            return None
        payload = json.dumps(ticket, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            self.config.TICKET_EXTERNAL_API_URL,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            external_id = body.get("ticket_id") or body.get("id")
            logger.info("外部工单同步成功: %s -> %s", ticket["ticket_no"], external_id)
            return str(external_id) if external_id else None
        except (urllib.error.URLError, json.JSONDecodeError, TimeoutError) as e:
            logger.error("外部工单同步失败: %s", e)
            return None

    def update_ticket_status(self, ticket_no: str, status: str) -> bool:
        """工单状态流转：pending -> in_progress -> resolved / closed。"""
        if status not in TICKET_STATUS:
            logger.error("非法工单状态 '%s'", status)
            return False
        if not self.db:
            logger.warning("MySQL 不可用，无法更新工单状态 %s", ticket_no)
            return False
        try:
            with self.db.cursor() as cur:
                cur.execute("UPDATE tickets SET status=%s WHERE ticket_no=%s", (status, ticket_no))
            self.db.commit()
            logger.info("工单 %s 状态流转为 %s", ticket_no, status)
            return True
        except pymysql.MySQLError as e:
            logger.error("工单状态更新失败: %s", e)
            self.db.rollback()
            return False

    # ---- 反馈 ----

    def save_feedback(
        self,
        session_id: str,
        query: str,
        user_id: str,
        rating: int,
        comment: str | None,
        need_human: bool,
        ticket_no: str | None = None,
    ) -> None:
        """反馈落库；kb_status=open 供知识库闭环（T1 数据组消费）回写。"""
        if self.db:
            try:
                with self.db.cursor() as cur:
                    cur.execute(
                        """INSERT INTO feedback
                           (session_id, query, user_id, rating, comment, need_human, ticket_no)
                           VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                        (session_id, query, user_id, rating, comment, int(need_human), ticket_no),
                    )
                self.db.commit()
            except pymysql.MySQLError as e:
                logger.error("反馈落库失败: %s", e)
                self.db.rollback()
        logger.info(
            "反馈落库: session=%s rating=%d need_human=%s ticket=%s",
            session_id, rating, need_human, ticket_no,
        )

    def handle_feedback(
        self, session_id: str, query: str, user_id: str, team: str,
        rating: int, comment: str | None, need_human: bool,
    ) -> dict:
        """反馈入口：落库；need_human=true 时创建工单，返回 {status, ticket_id}。"""
        ticket_no = None
        if need_human:
            ticket = self.create_ticket(session_id, query, user_id, team, reason="user_request")
            ticket_no = ticket["ticket_no"]
        self.save_feedback(session_id, query, user_id, rating, comment, need_human, ticket_no)
        return {"status": "success", "ticket_id": ticket_no}
