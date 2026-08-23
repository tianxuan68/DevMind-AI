"""BM25 FAQ 检索（T5）。

对外接口：
    faq_match(query: str) -> FAQHit | None
命中即秒回，低于置信度阈值返回 None 走 RAG 主链路。

实现说明：
- 使用 rank-bm25 的 BM25Plus
- FAQ 索引文本 = 标准问题 + 关键词/同义词
- score 为归一化后的匹配置信度（0~1），与 config.ini 中
  [retrieval].confidence_threshold 比较决定是否命中
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable

from rank_bm25 import BM25Plus

from mysql_qa.utils.preprocess import build_searchable_text, normalize_text, tokenize

logger = logging.getLogger("devmind-ai.mysql_qa.bm25_search")


@dataclass
class FAQHit:
    """FAQ 精确匹配命中结果。

    对外契约字段：answer / source / score。
    其余字段用于调试与后续转人工/审计。
    """
    answer: str
    source: str
    score: float
    question: str = ""
    faq_id: int | str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


def _default_confidence_threshold() -> float:
    try:
        from base.config import Config
        return Config().CONFIDENCE_THRESHOLD
    except Exception:
        return 0.75


class BM25Search:
    """基于 MySQL FAQ 表数据构建的 BM25 精确/模糊匹配器。"""

    def __init__(
        self,
        redis_client: Any | None = None,
        mysql_client: Any | None = None,
        faqs: list[dict[str, Any]] | None = None,
        tokenizer: Callable[[str], list[str]] | None = None,
        confidence_threshold: float | None = None,
        top_k: int = 1,
        k1: float = 1.5,
        b: float = 0.75,
        min_query_tokens: int = 2,
        ambiguity_ratio: float = 0.9,
        enforce_filter: bool = False,
    ) -> None:
        self.redis_client = redis_client
        self.mysql_client = mysql_client
        self.tokenizer = tokenizer or tokenize
        self.confidence_threshold = (
            confidence_threshold
            if confidence_threshold is not None
            else _default_confidence_threshold()
        )
        self.top_k = max(1, int(top_k))
        self.k1 = k1
        self.b = b
        self.min_query_tokens = max(1, int(min_query_tokens))
        self.ambiguity_ratio = float(ambiguity_ratio)
        self.enforce_filter = bool(enforce_filter)
        self.faqs: list[dict[str, Any]] = []
        if faqs is not None:
            self.faqs = [dict(item) for item in faqs if self._is_valid_faq(dict(item))]
        elif mysql_client is not None:
            self.faqs = [dict(item) for item in mysql_client.load_faqs() if self._is_valid_faq(dict(item))]
        self._build_index()

    def _build_index(self) -> None:
        """根据当前 faqs 重建 BM25 索引。"""
        self._doc_texts = [build_searchable_text(faq) for faq in self.faqs]
        self._tokenized_docs = [self.tokenizer(text) for text in self._doc_texts]
        if self._tokenized_docs:
            self._bm25 = BM25Plus(self._tokenized_docs, k1=self.k1, b=self.b, delta=1.0)
        else:
            self._bm25 = None
            logger.warning("FAQ 索引为空，faq_match 将始终返回 None")

    def reload(self, faqs: list[dict[str, Any]] | None = None) -> None:
        """重新加载 FAQ 并重建索引。

        - 传入 faqs 时使用内存数据
        - 未传入但存在 mysql_client 时从 MySQL 重新加载
        """
        if faqs is not None:
            self.faqs = [dict(item) for item in faqs if self._is_valid_faq(dict(item))]
        elif self.mysql_client is not None:
            self.faqs = [dict(item) for item in self.mysql_client.load_faqs() if self._is_valid_faq(dict(item))]
        self._build_index()

    def add_faq(self, faq: dict[str, Any]) -> None:
        """追加一条 FAQ 并重建索引（MVP 阶段数据量小，直接重建）。"""
        faq = dict(faq)
        if not self._is_valid_faq(faq):
            logger.warning("FAQ 无效，未加入索引: %s", faq.get("question"))
            return
        self.faqs.append(faq)
        self._build_index()

    @staticmethod
    def _faq_question(faq: dict[str, Any]) -> str:
        return (
            faq.get("question")
            or faq.get("standard_question")
            or faq.get("title")
            or ""
        )

    @staticmethod
    def _faq_answer(faq: dict[str, Any]) -> str:
        return faq.get("answer") or faq.get("standard_answer") or ""

    @staticmethod
    def _faq_source(faq: dict[str, Any]) -> str:
        return (
            faq.get("source")
            or faq.get("doc_source")
            or faq.get("document_source")
            or faq.get("url")
            or ""
        )


    @staticmethod
    def _is_valid_faq(faq: dict[str, Any]) -> bool:
        """FAQ 必须包含标准问题、标准答案和文档出处，否则不进入索引。"""
        question = BM25Search._faq_question(faq)
        answer = BM25Search._faq_answer(faq)
        source = BM25Search._faq_source(faq)
        if not question or not answer or not source:
            logger.warning(
                "跳过无效 FAQ：question/answer/doc_source 不能为空，faq=%s",
                faq.get("id") or faq.get("question"),
            )
            return False
        return True

    @staticmethod
    def _match_filter(faq: dict[str, Any], filter: dict[str, Any]) -> bool:
        """判断 FAQ 是否满足权限/团队等元数据过滤条件。"""
        for key, value in filter.items():
            actual = faq.get(key)
            if isinstance(value, (list, tuple, set)):
                if actual not in value:
                    return False
            elif actual != value:
                return False
        return True

    def _confidence(
        self,
        query: str,
        query_tokens: list[str],
        doc_index: int,
        raw_scores: list[float],
        allowed_indices: list[int] | None = None,
    ) -> float:
        """将 BM25 原始分转换为 0~1 匹配置信度。

        策略：
        1. 标准问题归一化后完全一致 -> 1.0
        2. 否则综合查询词覆盖率（0.7）与 top1 相对优势（0.3）
        """
        normalized_query = normalize_text(query)
        normalized_question = normalize_text(self._faq_question(self.faqs[doc_index]))
        if normalized_query and normalized_query == normalized_question:
            return 1.0

        # 非精确命中时，过短的泛词查询不返回结果，避免“连接/服务/权限”误命中
        if len(query_tokens) < self.min_query_tokens:
            return 0.0

        max_raw = float(raw_scores[doc_index])
        candidate_scores = (
            [float(raw_scores[i]) for i in allowed_indices]
            if allowed_indices is not None
            else [float(s) for s in raw_scores]
        )
        second_raw = (
            sorted(candidate_scores, reverse=True)[1]
            if len(candidate_scores) > 1
            else 0.0
        )
        # 多个 FAQ 分数非常接近时视为歧义，不硬答
        if max_raw > 0 and second_raw > 0 and (second_raw / max_raw) >= self.ambiguity_ratio:
            return 0.0

        query_set = set(query_tokens)
        if not query_set:
            return 0.0

        doc_tokens = set(self._tokenized_docs[doc_index])
        coverage = len(query_set & doc_tokens) / len(query_set)
        rank_conf = max_raw / (max_raw + max(0.0, second_raw) + 1e-9)
        confidence = 0.7 * coverage + 0.3 * rank_conf
        return round(min(1.0, confidence), 4)

    def _to_hit(self, doc_index: int, score: float) -> FAQHit:
        faq = self.faqs[doc_index]
        return FAQHit(
            answer=self._faq_answer(faq),
            source=self._faq_source(faq),
            score=score,
            question=self._faq_question(faq),
            faq_id=faq.get("id"),
            metadata=dict(faq),
        )

    def search(
        self,
        query: str,
        top_k: int | None = None,
        min_score: float | None = None,
        filter: dict[str, Any] | None = None,
    ) -> list[FAQHit]:
        """返回超过阈值的 top_k 个 FAQHit；低于阈值的结果不会返回。"""
        if self.enforce_filter and not filter:
            raise ValueError("FAQ 查询必须传入权限过滤条件 filter")

        if self._bm25 is None:
            return []

        top_k = max(1, int(top_k or self.top_k))
        threshold = self.confidence_threshold if min_score is None else min_score
        query_tokens = self.tokenizer(query)
        if not query_tokens:
            return []

        raw_scores = self._bm25.get_scores(query_tokens)
        if len(raw_scores) == 0:
            return []

        allowed_indices: list[int] | None = None
        if filter:
            allowed_indices = [
                i for i, faq in enumerate(self.faqs)
                if self._match_filter(faq, filter)
            ]
            if not allowed_indices:
                return []

        ranked = sorted(
            allowed_indices if allowed_indices is not None else range(len(raw_scores)),
            key=lambda i: float(raw_scores[i]),
            reverse=True,
        )
        hits: list[FAQHit] = []
        for doc_index in ranked[:top_k]:
            score = self._confidence(
                query, query_tokens, doc_index, raw_scores, allowed_indices
            )
            if score >= threshold:
                hit = self._to_hit(doc_index, score)
                # 兜底：禁止返回无出处结果
                if not hit.source:
                    logger.warning("FAQ 命中但缺少出处，跳过: id=%s", hit.faq_id)
                    continue
                hits.append(hit)
        return hits

    def faq_match(self, query: str, filter: dict[str, Any] | None = None) -> FAQHit | None:
        """对外主接口：命中返回 FAQHit，未命中或低置信度返回 None。"""
        hits = self.search(query, top_k=1, filter=filter)
        return hits[0] if hits else None


def faq_match(query: str, filter: dict[str, Any] | None = None) -> FAQHit | None:
    """模块级便捷入口，等价于 mysql_qa.sql_main.faq_match。"""
    from .sql_main import faq_match as _sql_faq_match

    return _sql_faq_match(query, filter=filter)
