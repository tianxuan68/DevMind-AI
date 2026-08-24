"""MySQL FAQ 问答主模块（T5）。

对外接口：
    faq_match(query: str, filter: dict | None = None) -> FAQHit | None
    get_faq_searcher(force_refresh: bool = False) -> BM25Search
    refresh_faq_searcher() -> BM25Search
    reset_faq_searcher() -> None

首次调用 faq_match 时自动加载 MySQL FAQ 表并构建 BM25 索引；
MySQL 不可用时抛出 FAQStoreUnavailableError，避免把故障伪装成“未命中”。
"""
from __future__ import annotations

import logging
import time

from .db.mysql_client import MySQLClient
from .errors import FAQStoreUnavailableError
from .retrieval.bm25_search import BM25Search, FAQHit

logger = logging.getLogger("devmind-ai.mysql_qa.sql_main")

_searcher: BM25Search | None = None
_searcher_loaded_at: float = 0.0
_REFRESH_INTERVAL_SECONDS = 300.0


def get_faq_searcher(force_refresh: bool = False) -> BM25Search:
    """获取全局 FAQ BM25 检索器。

    - 默认带 TTL 自动刷新（300 秒）
    - force_refresh=True 时强制从 MySQL 重新加载
    - MySQL 不可用且没有旧索引时抛出 FAQStoreUnavailableError
    - MySQL 刷新失败但已有旧索引时保留旧索引并告警
    """
    global _searcher, _searcher_loaded_at

    now = time.monotonic()
    if _searcher is not None and not force_refresh:
        if _searcher.mysql_client is None or (now - _searcher_loaded_at) < _REFRESH_INTERVAL_SECONDS:
            return _searcher

    if force_refresh and _searcher is not None and _searcher.mysql_client is None:
        # 内存注入的 searcher 不从 MySQL 刷新
        return _searcher

    try:
        client = MySQLClient()
        new_searcher = BM25Search(mysql_client=client)
    except Exception as exc:
        if _searcher is not None:
            logger.warning("FAQ 刷新失败，继续使用旧索引", exc_info=True)
            return _searcher
        logger.exception("初始化 FAQ BM25 检索器失败")
        raise FAQStoreUnavailableError("FAQ 数据库不可用或加载失败") from exc

    _searcher = new_searcher
    _searcher_loaded_at = now
    logger.info("FAQ BM25 检索器已加载，共 %s 条 FAQ", len(_searcher.faqs))
    return _searcher


def refresh_faq_searcher() -> BM25Search:
    """强制刷新 FAQ 索引，供 T1 导入/更新 FAQ 后调用。"""
    return get_faq_searcher(force_refresh=True)


def reset_faq_searcher() -> None:
    """重置全局检索器，便于测试/热加载。"""
    global _searcher, _searcher_loaded_at
    _searcher = None
    _searcher_loaded_at = 0.0


def faq_match(query: str, filter: dict | None = None) -> FAQHit | None:
    """T5 对外接口：高频 FAQ 精确匹配。

    命中返回 FAQHit（answer/source/score），未命中或低于置信度返回 None。
    filter 可选：按 team / security_level 等元数据过滤，用于权限隔离。
    """
    return get_faq_searcher().faq_match(query, filter=filter)
