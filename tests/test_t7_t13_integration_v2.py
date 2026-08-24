"""T7/T13 兼容测试：T6 二类 + T8 英文七类 slug 路由。

当前 intent_classifier 为二类（技术咨询 / 通用知识）；
search_strategy / query_rewrite / rag_generator 同时兼容 T8 规则降级的英文 slug。
"""
from __future__ import annotations

import os
import sys
import unittest
from dataclasses import fields
from unittest.mock import patch

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

# T8 英文 slug（不依赖 intent_classifier 七类常量）
CAT_TECH_EN = "tech"
CAT_ACCESS = "access_request"
CAT_INCIDENT = "incident"
CAT_TICKET = "ticket_inquiry"
CAT_COMPLAINT = "complaint_suggestion"
CAT_POLICY = "policy_general"
CAT_COMMON = "common"


class TestContracts(unittest.TestCase):
    def test_imports(self):
        from internal_kb_qa.core.intent_classifier import (
            CATEGORY_GENERAL,
            CATEGORY_TECH,
            Classification,
            classify,
        )
        from internal_kb_qa.core.query_rewrite import RewrittenQuery, query_rewrite
        from internal_kb_qa.core.rag_generator import RAGResult, prepare_rag_context, rag_answer
        from internal_kb_qa.core.search_strategy import SearchStrategy, build_search_strategy
        from rag_qa.core.strategy_selector import StrategySelector

        self.assertEqual(CATEGORY_TECH, "技术咨询")
        self.assertEqual(CATEGORY_GENERAL, "通用知识")
        self.assertTrue(callable(classify))
        self.assertTrue(callable(build_search_strategy))
        self.assertTrue(callable(query_rewrite))
        self.assertTrue(callable(rag_answer))
        self.assertTrue(callable(prepare_rag_context))
        self.assertTrue(hasattr(StrategySelector, "STRATEGY_DIRECT"))
        self.assertEqual(Classification.__name__, "Classification")
        self.assertEqual(SearchStrategy.__name__, "SearchStrategy")
        self.assertEqual(RewrittenQuery.__name__, "RewrittenQuery")
        self.assertEqual(RAGResult.__name__, "RAGResult")

        try:
            from internal_kb_qa.core.hybrid_search import search
            from internal_kb_qa.core.reranker import rerank

            self.assertTrue(callable(rerank))
            self.assertTrue(callable(search))
        except OSError as exc:
            self.skipTest(f"torch/模型环境不可用，跳过 T4/T7 重依赖导入: {exc}")

    def test_rag_result_fields(self):
        from internal_kb_qa.core.rag_generator import RAGResult

        names = {f.name for f in fields(RAGResult)}
        for required in ("answer", "sources", "confidence", "need_human"):
            self.assertIn(required, names)

    def test_rewritten_query_fields(self):
        from internal_kb_qa.core.query_rewrite import RewrittenQuery

        names = {f.name for f in fields(RewrittenQuery)}
        for required in ("rewritten_query", "sub_queries", "filters", "search_queries"):
            self.assertIn(required, names)

    def test_search_strategy_fields(self):
        from internal_kb_qa.core.search_strategy import SearchStrategy

        names = {f.name for f in fields(SearchStrategy)}
        for required in ("strategy", "top_k", "use_rerank", "filters"):
            self.assertIn(required, names)


class TestSearchStrategy(unittest.TestCase):
    def test_tech_cn_hybrid(self):
        from internal_kb_qa.core.intent_classifier import CATEGORY_TECH
        from internal_kb_qa.core.search_strategy import build_search_strategy

        s = build_search_strategy("MySQL 连接池配置", CATEGORY_TECH)
        self.assertEqual(s.strategy, "hybrid")
        self.assertTrue(s.use_rerank)

    def test_general_cn_none(self):
        from internal_kb_qa.core.intent_classifier import CATEGORY_GENERAL
        from internal_kb_qa.core.search_strategy import build_search_strategy

        s = build_search_strategy("今天天气怎么样", CATEGORY_GENERAL)
        self.assertEqual(s.strategy, "none")
        self.assertFalse(s.use_rerank)

    def test_english_slug_routes(self):
        from internal_kb_qa.core.search_strategy import build_search_strategy

        cases = [
            (CAT_TECH_EN, "hybrid", True),
            (CAT_ACCESS, "hybrid", True),
            (CAT_INCIDENT, "runbook", True),
            (CAT_TICKET, "none", False),
            (CAT_COMPLAINT, "none", False),
            (CAT_POLICY, "none", False),
            (CAT_COMMON, "none", False),
        ]
        for category, expected, rerank in cases:
            s = build_search_strategy("q", category)
            self.assertEqual(s.strategy, expected, category)
            self.assertEqual(s.use_rerank, rerank, category)


class TestPipelineMocked(unittest.TestCase):
    def _mock_hit(self):
        from internal_kb_qa.core.hit import Hit

        return Hit(
            text="MySQL 连接池 max_connections 默认值为 151，可在 my.cnf 中调整。",
            score=0.92,
            metadata={"source": "wiki-mysql.md", "page": 3},
        )

    @patch("internal_kb_qa.core.rag_generator._call_llm_sync")
    @patch("internal_kb_qa.core.rag_generator._run_rag_pipeline")
    def test_tech_rag_pipeline(self, mock_pipeline, mock_llm):
        from internal_kb_qa.core.intent_classifier import CATEGORY_TECH
        from internal_kb_qa.core.query_rewrite import RewrittenQuery
        from internal_kb_qa.core.rag_generator import rag_answer
        from internal_kb_qa.core.search_strategy import SearchStrategy
        from rag_qa.core.strategy_selector import StrategySelector

        mock_hits = [self._mock_hit()]
        mock_pipeline.return_value = (
            mock_hits,
            RewrittenQuery(
                rewritten_query="MySQL 连接池默认配置",
                search_queries=["MySQL 连接池默认配置"],
                advanced_strategy=StrategySelector.STRATEGY_DIRECT,
            ),
            SearchStrategy(strategy="hybrid", top_k=5, use_rerank=True),
        )
        mock_llm.return_value = "根据文档，MySQL 连接池 max_connections 默认 151。[来源: wiki-mysql.md, 第3页]"

        result = rag_answer(
            "测试环境 MySQL 连接池默认配置是多少？",
            category=CATEGORY_TECH,
        )

        self.assertFalse(result.need_human)
        self.assertGreater(result.confidence, 0)
        self.assertGreater(len(result.sources), 0)
        self.assertIn("151", result.answer)
        mock_pipeline.assert_called_once()
        mock_llm.assert_called_once()

    @patch("internal_kb_qa.core.rag_generator._call_llm_sync")
    @patch("internal_kb_qa.core.rag_generator._run_rag_pipeline")
    def test_policy_general_direct_llm_no_search(self, mock_pipeline, mock_llm):
        from internal_kb_qa.core.rag_generator import rag_answer

        mock_llm.return_value = "公司年假是 10 天。"

        result = rag_answer("公司年假有多少天？", category=CAT_POLICY)
        mock_pipeline.assert_not_called()

        self.assertFalse(result.need_human)
        self.assertEqual(result.sources, [])
        mock_llm.assert_called_once()

    @patch("internal_kb_qa.core.rag_generator._call_llm_sync")
    @patch("internal_kb_qa.core.rag_generator._run_rag_pipeline")
    def test_common_direct_llm_no_search(self, mock_pipeline, mock_llm):
        from internal_kb_qa.core.rag_generator import rag_answer

        mock_llm.return_value = "今天天气不错。"

        result = rag_answer("今天天气怎么样？", category=CAT_COMMON)
        mock_pipeline.assert_not_called()

        self.assertFalse(result.need_human)
        self.assertEqual(result.sources, [])
        mock_llm.assert_called_once()

    def test_ticket_inquiry_need_human(self):
        from internal_kb_qa.core.rag_generator import rag_answer

        result = rag_answer("我提交的工单处理到哪一步了？", category=CAT_TICKET)
        self.assertTrue(result.need_human)
        self.assertEqual(result.sources, [])

    def test_complaint_need_human(self):
        from internal_kb_qa.core.rag_generator import rag_answer

        result = rag_answer("这个系统太难用了", category=CAT_COMPLAINT)
        self.assertTrue(result.need_human)
        self.assertEqual(result.sources, [])

    @patch("internal_kb_qa.core.query_rewrite._call_llm_sync")
    def test_query_rewrite_direct_strategy(self, mock_llm):
        from internal_kb_qa.core.intent_classifier import CATEGORY_TECH
        from internal_kb_qa.core.query_rewrite import query_rewrite
        from rag_qa.core.strategy_selector import StrategySelector

        mock_llm.return_value = '{"rewritten_query": "Redis 服务不可用排查", "sub_queries": []}'

        rw = query_rewrite(
            "Redis 挂了怎么办",
            category=CATEGORY_TECH,
            advanced_strategy=StrategySelector.STRATEGY_DIRECT,
        )
        self.assertTrue(rw.search_queries)
        self.assertEqual(rw.advanced_strategy, StrategySelector.STRATEGY_DIRECT)

    def test_query_rewrite_no_search_categories(self):
        from internal_kb_qa.core.query_rewrite import query_rewrite

        for category in (CAT_TICKET, CAT_COMPLAINT, CAT_POLICY, CAT_COMMON):
            rw = query_rewrite("今天天气怎么样？", category=category)
            self.assertEqual(rw.search_queries, [], f"{category} 不应产生检索 query")


if __name__ == "__main__":
    unittest.main()
