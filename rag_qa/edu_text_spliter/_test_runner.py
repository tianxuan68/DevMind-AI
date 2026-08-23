"""T3 自动化测试（调用 internal_kb_qa 实现）。"""
import os
import sys
import traceback

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, PROJECT_ROOT)

from internal_kb_qa.core.models import Document
from internal_kb_qa.text_splitters import save_chunks_json, split


def main() -> int:
    try:
        base = {
            "team": "backend",
            "system": "user-service",
            "version": "2.3.0",
            "last_updated": "2026-08-20T10:00:00",
            "security_level": "team",
            "page": 1,
        }
        runbook = """# 用户服务部署手册
## 环境要求
服务依赖 JDK 17 与 MySQL 8.0。

## 启动命令

```bash
java -jar user-service.jar
```

## 回滚策略
若出现 5xx 异常，请立即回滚。"""

        docs = [
            Document(page_content=runbook, metadata={**base, "source": "runbook.md", "doc_type": "runbook"}),
            Document(
                page_content="class A:\n    def foo(self): pass",
                metadata={**base, "source": "a.py", "doc_type": "api"},
            ),
        ]
        chunks = split(docs)
        assert chunks, "split 结果为空"
        assert all(c.metadata.get("team") for c in chunks), "缺少 team 元数据"
        out = os.path.join(os.path.dirname(__file__), "_split_result.json")
        save_chunks_json(chunks, out)
        print(f"PASS: {len(chunks)} chunks -> {out}")
        return 0
    except Exception:
        print(traceback.format_exc())
        return 1


if __name__ == "__main__":
    sys.exit(main())
