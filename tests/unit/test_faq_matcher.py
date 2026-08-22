"""T5 高频 FAQ 精确匹配单元测试。"""
from __future__ import annotations

import pytest

import pytest

from internal_kb_qa.core.faq_matcher import FAQHit, FAQMatcher
from mysql_qa.errors import FAQStoreUnavailableError
from mysql_qa.retrieval.bm25_search import BM25Search
from mysql_qa.utils.preprocess import normalize_text, tokenize

FAQ_LIST = [
    {
        "id": 1,
        "question": "如何部署服务",
        "answer": "执行 deploy.sh 完成部署",
        "source": "docs/deploy.md",
        "keywords": "部署 上线",
        "team": "backend",
        "security_level": "team",
    },
    {
        "id": 2,
        "question": "MySQL 连接失败怎么排查",
        "answer": "检查连接串和网络连通性",
        "source": "docs/mysql.md",
        "keywords": "mysql 连接 失败",
        "team": "ops",
        "security_level": "team",
    },
    {
        "id": 3,
        "question": "如何申请服务器权限",
        "answer": "提交权限申请工单",
        "source": "docs/permission.md",
        "keywords": "权限 申请",
        "team": "ops",
        "security_level": "team",
    },
]


@pytest.fixture()
def searcher() -> BM25Search:
    return BM25Search(faqs=FAQ_LIST, confidence_threshold=0.75)


def test_faq_match_exact_question_hit(searcher: BM25Search) -> None:
    hit = searcher.faq_match("如何部署服务")

    assert hit is not None
    assert isinstance(hit, FAQHit)
    assert hit.answer == "执行 deploy.sh 完成部署"
    assert hit.source == "docs/deploy.md"
    assert hit.score >= 0.75


def test_faq_match_fuzzy_hit(searcher: BM25Search) -> None:
    hit = searcher.faq_match("部署服务")

    assert hit is not None
    assert hit.faq_id == 1
    assert hit.score >= 0.75


def test_faq_match_unrelated_question_returns_none(searcher: BM25Search) -> None:
    assert searcher.faq_match("今天天气怎么样") is None


def test_faq_match_empty_query_returns_none(searcher: BM25Search) -> None:
    assert searcher.faq_match("") is None
    assert searcher.faq_match("   ") is None


def test_faq_match_empty_index_returns_none() -> None:
    searcher = BM25Search(faqs=[], confidence_threshold=0.75)
    assert searcher.faq_match("如何部署服务") is None


def test_search_returns_top_k_above_threshold(searcher: BM25Search) -> None:
    hits = searcher.search("MySQL连接失败", top_k=3)

    assert hits
    assert hits[0].faq_id == 2
    assert all(hit.score >= 0.75 for hit in hits)


def test_faq_matcher_facade() -> None:
    matcher = FAQMatcher(faqs=FAQ_LIST, confidence_threshold=0.75)

    hit = matcher.faq_match("如何申请服务器权限")
    assert hit is not None
    assert hit.source == "docs/permission.md"

    assert matcher("今天天气怎么样") is None


def test_preprocess_normalize_and_tokenize() -> None:
    assert normalize_text("  MySQL 连接失败？ ") == "mysql 连接失败"
    assert normalize_text("如何部署服务?") == "如何部署服务"
    assert "mysql" in tokenize("MySQL 连接失败")
    assert "连接" in tokenize("MySQL 连接失败")


def test_faq_match_halfwidth_question_mark_exact_hit() -> None:
    searcher = BM25Search(faqs=FAQ_LIST, confidence_threshold=0.75)
    hit = searcher.faq_match("如何部署服务?")
    assert hit is not None
    assert hit.faq_id == 1
    assert hit.score == 1.0


def test_faq_match_respects_metadata_filter() -> None:
    searcher = BM25Search(faqs=FAQ_LIST, confidence_threshold=0.75)

    # 无过滤时命中 backend 团队 FAQ
    assert searcher.faq_match("如何部署服务") is not None

    # 过滤为 ops 团队时，backend FAQ 不应命中
    assert searcher.faq_match("如何部署服务", filter={"team": "ops"}) is None

    # 过滤为 backend 团队时命中
    hit = searcher.faq_match("如何部署服务", filter={"team": "backend"})
    assert hit is not None
    assert hit.faq_id == 1


def test_generic_single_word_does_not_match() -> None:
    searcher = BM25Search(faqs=FAQ_LIST, confidence_threshold=0.75)
    for query in ["连接", "服务", "权限"]:
        assert searcher.faq_match(query) is None


def test_faq_without_source_or_answer_is_not_indexed() -> None:
    faqs = [
        {"id": 1, "question": "无答案问题", "answer": "", "doc_source": "docs/x.md"},
        {"id": 2, "question": "无出处问题", "answer": "有答案", "doc_source": ""},
        {"id": 3, "question": "正常问题", "answer": "有答案", "doc_source": "docs/y.md"},
    ]
    searcher = BM25Search(faqs=faqs, confidence_threshold=0.75)

    assert len(searcher.faqs) == 1
    assert searcher.faq_match("无答案问题") is None
    assert searcher.faq_match("无出处问题") is None
    assert searcher.faq_match("正常问题") is not None


def test_enforce_filter_requires_filter() -> None:
    matcher = FAQMatcher(
        faqs=FAQ_LIST,
        confidence_threshold=0.75,
        enforce_filter=True,
    )

    with pytest.raises(ValueError):
        matcher.faq_match("如何部署服务")

    hit = matcher.faq_match("如何部署服务", {"team": "backend"})
    assert hit is not None
    assert hit.faq_id == 1


def test_mysql_failure_raises_store_unavailable(monkeypatch) -> None:
    import mysql_qa.sql_main as sql_main

    sql_main.reset_faq_searcher()

    class Boom:
        def __init__(self):
            raise RuntimeError("db down")

    monkeypatch.setattr(sql_main, "MySQLClient", Boom)

    with pytest.raises(FAQStoreUnavailableError):
        sql_main.get_faq_searcher()

    sql_main.reset_faq_searcher()
