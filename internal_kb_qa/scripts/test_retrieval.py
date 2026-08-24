"""检索验证脚本：对 Milvus 混合检索做多次查询验证。"""
from __future__ import annotations

import argparse
import sys

from internal_kb_qa.core.hybrid_search import search


DEFAULT_QUERIES = [
    ("Python 项目环境初始化", None),
    ("MySQL 连接池默认配置", "infra"),
    ("Java 命名规范", "backend"),
    ("生产环境故障排查流程", "ops"),
    ("如何提交权限申请", "infra"),
]


def run_queries(queries: list[tuple[str, str | None]], top_k: int) -> int:
    failed = 0
    for index, (query, source_filter) in enumerate(queries, start=1):
        print(f"\n=== Query {index}: {query} | filter={source_filter or 'ALL'} ===")
        try:
            hits = search(query, top_k=top_k, filter={"source": source_filter} if source_filter else None)
        except Exception as exc:
            failed += 1
            print(f"[FAIL] {exc}")
            continue
        if not hits:
            failed += 1
            print("[FAIL] 未召回任何结果")
            continue
        for rank, hit in enumerate(hits, start=1):
            preview = hit.text.replace("\n", " ")[:120]
            print(f"[{rank}] score={hit.score:.3f} source={hit.metadata.get('source')} text={preview}...")
        print(f"[OK] 返回 {len(hits)} 条")
    return failed


def main() -> int:
    parser = argparse.ArgumentParser(description="验证 Milvus 混合检索")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--query", action="append", help="自定义查询，可重复")
    args = parser.parse_args()

    if args.query:
        queries = [(item, None) for item in args.query]
    else:
        queries = DEFAULT_QUERIES

    failed = run_queries(queries, top_k=args.top_k)
    if failed:
        print(f"\n[RESULT] 失败 {failed}/{len(queries)} 条查询")
        return 1
    print(f"\n[RESULT] 全部 {len(queries)} 条查询通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
