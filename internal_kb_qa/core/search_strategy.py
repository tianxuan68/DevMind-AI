"""T13 检索策略路由。

对外接口：
    build_search_strategy(query: str, category: str) -> SearchStrategy
策略：hybrid / runbook / none（与 T6 七类意图对齐）
"""
from __future__ import annotations

from dataclasses import dataclass, field

from base.config import Config
from internal_kb_qa.core.intent_classifier import (
    CATEGORY_ACCESS_REQUEST,
    CATEGORY_COMMON,
    CATEGORY_COMPLAINT_SUGGESTION,
    CATEGORY_INCIDENT,
    CATEGORY_POLICY_GENERAL,
    CATEGORY_TECH,
    CATEGORY_TICKET_INQUIRY,
)


@dataclass
class SearchStrategy:
    strategy: str          # hybrid / runbook / none
    top_k: int
    use_rerank: bool
    filters: dict = field(default_factory=dict)


# 七类意图 -> 检索策略（与 T6 v2 意图分类对齐）
_CATEGORY_STRATEGY = {
    CATEGORY_TECH: "hybrid",               # 技术咨询：混合检索 + RAG
    CATEGORY_ACCESS_REQUEST: "hybrid",     # 权限/账号申请：混合检索 + 权限过滤
    CATEGORY_INCIDENT: "runbook",          # 故障上报：值班手册优先
    CATEGORY_TICKET_INQUIRY: "none",       # 工单/进度查询：不检索，转工单
    CATEGORY_COMPLAINT_SUGGESTION: "none",  # 投诉/建议：不检索，转人工
    CATEGORY_POLICY_GENERAL: "none",       # 制度/通用知识：不检索，直接 LLM
    CATEGORY_COMMON: "none",               # 闲聊：不检索，直接 LLM
}

# 需要进入 T7 重排的策略
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
        ("我需要申请生产环境数据库只读账号", CATEGORY_ACCESS_REQUEST, "hybrid"),
        ("线上服务突然大量 502 报错", CATEGORY_INCIDENT, "runbook"),
        ("我提交的工单现在处理到哪一步了？", CATEGORY_TICKET_INQUIRY, "none"),
        ("这个系统太难用了，我要投诉", CATEGORY_COMPLAINT_SUGGESTION, "none"),
        ("公司年假有多少天？", CATEGORY_POLICY_GENERAL, "none"),
        ("今天天气怎么样？", CATEGORY_COMMON, "none"),
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
