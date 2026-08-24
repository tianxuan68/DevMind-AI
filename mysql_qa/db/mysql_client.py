"""MySQL 客户端（T5）。

负责连接 internal_tech_kb 库，并提供 FAQ 表的读取/新增/更新/删除能力。
T8/T10 的工单/反馈表 CRUD 由对应任务在 service 层继续扩展。

对外能力：
    load_faqs(team=None, security_level=None) -> list[dict]
    get_faq(faq_id) -> dict | None
    add_faq(faq) -> int
    update_faq(faq_id, fields) -> bool
    delete_faq(faq_id) -> bool
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

import pymysql
import pymysql.cursors

try:
    from base.config import Config
except Exception:  # pragma: no cover - 独立运行 mysql_qa 时允许不依赖 base
    Config = None

logger = logging.getLogger("devmind-ai.mysql_qa.mysql_client")

_TABLE_NAME_RE = re.compile(r"^[A-Za-z0-9_]+$")


def _quote_identifier(name: str) -> str:
    if not _TABLE_NAME_RE.fullmatch(name):
        raise ValueError(f"非法表名: {name}")
    return f"`{name}`"


def _normalize_faq_fields(fields: dict[str, Any]) -> dict[str, Any]:
    """兼容旧字段名：source -> doc_source。"""
    fields = dict(fields)
    if "source" in fields and "doc_source" not in fields:
        fields["doc_source"] = fields.pop("source")
    return fields


class MySQLClient:
    """轻量 MySQL 客户端，默认读取 config.ini 中的 [mysql] 配置。"""

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        user: str | None = None,
        password: str | None = None,
        database: str | None = None,
        table_name: str = "faq",
        config_file: str = "config.ini",
        connect_timeout: int = 5,
    ) -> None:
        cfg = None
        if Config is not None:
            try:
                cfg = Config(config_file)
            except Exception:
                logger.warning("读取 config.ini 失败，使用默认 MySQL 配置", exc_info=True)

        self.host = host or (cfg.MYSQL_HOST if cfg else None) or "localhost"
        self.port = int(port or (cfg.config.getint("mysql", "port", fallback=3306) if cfg else 3306) or 3306)
        self.user = user or (cfg.MYSQL_USER if cfg else None) or "root"
        self.password = password if password is not None else (cfg.MYSQL_PASSWORD if cfg else "") or ""
        self.database = database or (cfg.MYSQL_DATABASE if cfg else None) or "internal_tech_kb"
        self.table_name = table_name
        self.connect_timeout = connect_timeout
        self.autocommit = True

    def _connect(self) -> pymysql.connections.Connection:
        return pymysql.connect(
            host=self.host,
            port=self.port,
            user=self.user,
            password=self.password,
            database=self.database,
            charset="utf8mb4",
            cursorclass=pymysql.cursors.DictCursor,
            autocommit=self.autocommit,
            connect_timeout=self.connect_timeout,
        )

    def ensure_schema(self) -> None:
        """按 mysql_qa/db/schema.sql 创建 FAQ 表（幂等）。"""
        schema_path = Path(__file__).with_name("schema.sql")
        statements = [
            stmt.strip()
            for stmt in schema_path.read_text(encoding="utf-8").split(";")
            if stmt.strip()
        ]
        with self._connect() as conn:
            with conn.cursor() as cursor:
                for statement in statements:
                    cursor.execute(statement)
        logger.info("FAQ 表结构已确保存在: %s", self.table_name)

    def load_faqs(
        self,
        team: str | None = None,
        security_level: str | None = None,
        include_inactive: bool = False,
    ) -> list[dict[str, Any]]:
        """加载 FAQ 表；可按 team / security_level 过滤。

        默认只加载 is_active=1 的有效 FAQ，避免过期/失效 FAQ 参与匹配。
        """
        sql = f"SELECT * FROM {_quote_identifier(self.table_name)}"
        conditions: list[str] = []
        params: list[Any] = []
        if not include_inactive:
            conditions.append("is_active = 1")
        if team:
            conditions.append("team = %s")
            params.append(team)
        if security_level:
            conditions.append("security_level = %s")
            params.append(security_level)
        if conditions:
            sql += " WHERE " + " AND ".join(conditions)
        sql += " ORDER BY id"

        logger.debug("执行 FAQ 查询: %s", sql)
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql, params)
                rows = cursor.fetchall()
        return [dict(row) for row in rows]

    def get_faq(self, faq_id: int | str) -> dict[str, Any] | None:
        """按 id 获取单条 FAQ。"""
        sql = f"SELECT * FROM {_quote_identifier(self.table_name)} WHERE id = %s LIMIT 1"
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql, (faq_id,))
                row = cursor.fetchone()
        return dict(row) if row else None

    def add_faq(self, faq: dict[str, Any]) -> int:
        """新增 FAQ，返回自增 id。"""
        if not faq:
            raise ValueError("FAQ 记录不能为空")
        faq = _normalize_faq_fields(faq)
        fields = list(faq.keys())
        placeholders = ", ".join(["%s"] * len(fields))
        sql = (
            f"INSERT INTO {_quote_identifier(self.table_name)} "
            f"({', '.join(_quote_identifier(f) for f in fields)}) VALUES ({placeholders})"
        )
        values = [faq[field] for field in fields]
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql, values)
                new_id = int(cursor.lastrowid)
        logger.info("新增 FAQ id=%s", new_id)
        return new_id

    def update_faq(self, faq_id: int | str, fields: dict[str, Any]) -> bool:
        """按 id 更新 FAQ 指定字段。"""
        if not fields:
            return False
        fields = _normalize_faq_fields(fields)
        assignments = ", ".join(f"{_quote_identifier(k)} = %s" for k in fields)
        sql = f"UPDATE {_quote_identifier(self.table_name)} SET {assignments} WHERE id = %s"
        values = list(fields.values()) + [faq_id]
        with self._connect() as conn:
            with conn.cursor() as cursor:
                affected = cursor.execute(sql, values)
        return affected > 0

    def delete_faq(self, faq_id: int | str) -> bool:
        """按 id 删除 FAQ。"""
        sql = f"DELETE FROM {_quote_identifier(self.table_name)} WHERE id = %s"
        with self._connect() as conn:
            with conn.cursor() as cursor:
                affected = cursor.execute(sql, (faq_id,))
        logger.info("删除 FAQ id=%s, affected=%s", faq_id, affected)
        return affected > 0
