"""T13 检索策略路由。

对外接口：
    build_search_strategy(query: str, category: str) -> SearchStrategy
策略：hybrid / runbook / none

与 T6 对齐：当前意图分类为二类（技术咨询 / 通用知识）；
同时兼容 T8 new_main 规则降级使用的英文七类 slug，避免合并后 ImportError。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from base.config import Config
from internal_kb_qa.core.intent_classifier import CATEGORY_GENERAL, CATEGORY_TECH


@dataclass
class SearchStrategy:
    strategy: str  # hybrid / runbook / none
    top_k: int
    use_rerank: bool
    filters: dict = field(default_factory=dict)


# 二类 + 英文七类兼容映射
_CATEGORY_STRATEGY = {
    CATEGORY_TECH: "hybrid",
    CATEGORY_GENERAL: "none",
    "tech": "hybrid",
    "access_request": "hybrid",
    "incident": "runbook",
    "ticket_inquiry": "none",
    "complaint_suggestion": "none",
    "policy_general": "none",
    "common": "none",
    "chitchat": "none",
}

_RERANK_STRATEGIES = {"hybrid", "runbook"}


def build_search_strategy(query: str, category: str) -> SearchStrategy:
    """根据 T6 意图分类结果，构建检索策略。"""
    conf = Config()
    strategy = _CATEGORY_STRATEGY.get(category, "hybrid")
    use_rerank = strategy in _RERANK_STRATEGIES

    return SearchStrategy(
        strategy=strategy,
        top_k=conf.TOP_K,
        use_rerank=use_rerank,
        filters={},
    )


def _main() -> None:
    """T13 本地测试：检索策略路由（无需 LLM / Milvus / 模型）。"""
    cases = [
        ("MySQL 连接池默认配置是多少？", CATEGORY_TECH, "hybrid"),
        ("今天天气怎么样？", CATEGORY_GENERAL, "none"),
        ("我需要申请生产环境数据库只读账号", "access_request", "hybrid"),
        ("线上服务突然大量 502 报错", "incident", "runbook"),
        ("我提交的工单现在处理到哪一步了？", "ticket_inquiry", "none"),
        ("这个系统太难用了，我要投诉", "complaint_suggestion", "none"),
        ("公司年假有多少天？", "policy_general", "none"),
        ("今天天气怎么样？", "common", "none"),
    ]
    passed = 0
    for query, category, expected in cases:
        s = build_search_strategy(query, category)
        ok = s.strategy == expected
        passed += int(ok)
        print(f"[{'PASS' if ok else 'FAIL'}] category={category!r} -> strategy={s.strategy!r} (期望 {expected!r})")
    print(f"\nT13 search_strategy: {passed}/{len(cases)} 通过")


if __name__ == "__main__":
    _main()
