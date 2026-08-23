"""T5 高频技术 FAQ 精确匹配。

对外接口：
    faq_match(query: str) -> FAQHit | None
命中即秒回，低于阈值返回 None 走 RAG 主链路。

本模块复用 mysql_qa 的 MySQL + BM25 检索能力，并封装为可注入
内存 FAQ 列表的 FAQMatcher，便于单元测试与离线评估。
"""
from __future__ import annotations

from typing import Any

from mysql_qa.db.mysql_client import MySQLClient
from mysql_qa.errors import FAQStoreUnavailableError
from mysql_qa.retrieval.bm25_search import BM25Search, FAQHit
from mysql_qa.sql_main import faq_match as _sql_faq_match
from mysql_qa.sql_main import refresh_faq_searcher as _refresh_faq_searcher

__all__ = [
    "FAQHit",
    "FAQMatcher",
    "FAQStoreUnavailableError",
    "faq_match",
    "get_faq_searcher",
    "refresh_faq_searcher",
    "reset_faq_searcher",
]


def faq_match(query: str, filter: dict[str, Any] | None = None) -> FAQHit | None:
    """T5 对外接口：高频 FAQ 精确匹配。"""
    return _sql_faq_match(query, filter=filter)


def get_faq_searcher() -> BM25Search:
    """获取全局 FAQ BM25 检索器。"""
    from mysql_qa.sql_main import get_faq_searcher as _get

    return _get()


def reset_faq_searcher() -> None:
    """重置全局 FAQ BM25 检索器。"""
    from mysql_qa.sql_main import reset_faq_searcher as _reset

    _reset()



def refresh_faq_searcher() -> BM25Search:
    """强制刷新全局 FAQ BM25 检索器。"""
    return _refresh_faq_searcher()


class FAQMatcher:
    """面向服务层/测试的可注入 FAQ 匹配器。

    用法：
        matcher = FAQMatcher(faqs=[...], confidence_threshold=0.75)
        hit = matcher.faq_match("如何部署服务")
    """

    def __init__(
        self,
        faqs: list[dict[str, Any]] | None = None,
        mysql_client: MySQLClient | None = None,
        confidence_threshold: float | None = None,
        top_k: int = 1,
        enforce_filter: bool = False,
    ) -> None:
        self._searcher = BM25Search(
            mysql_client=mysql_client,
            faqs=faqs,
            confidence_threshold=confidence_threshold,
            top_k=top_k,
            enforce_filter=enforce_filter,
        )

    def faq_match(self, query: str, filter: dict[str, Any] | None = None) -> FAQHit | None:
        return self._searcher.faq_match(query, filter=filter)

    def search(
        self,
        query: str,
        top_k: int | None = None,
        min_score: float | None = None,
        filter: dict[str, Any] | None = None,
    ) -> list[FAQHit]:
        return self._searcher.search(
            query, top_k=top_k, min_score=min_score, filter=filter
        )

    def __call__(self, query: str, filter: dict[str, Any] | None = None) -> FAQHit | None:
        return self.faq_match(query, filter=filter)
