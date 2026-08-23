"""T3 本地调试入口（兼容层，调用 internal_kb_qa 实现）。

用法：
    python -m rag_qa.edu_text_spliter.run_demo
    python -m internal_kb_qa.scripts.ingest_documents <path> --dry-run
"""
import logging
import os
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from internal_kb_qa.core.models import Document
from internal_kb_qa.core.vector_store import insert
from internal_kb_qa.text_splitters import save_chunks_json, split


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    runbook_md = """# 用户服务部署手册  
## 环境要求
服务依赖 JDK 17 与 MySQL 8.0，部署前请确认节点可用内存大于 4GB。

## 启动命令

```bash
java -jar user-service.jar --spring.profiles.active=prod
```

## 回滚策略
若新版本出现 5xx 异常，请立即切换至上一版本镜像并重启 Pod。"""

    python_code = """class UserService:
    def get_user(self, user_id: int):
        return self.repo.find_by_id(user_id)

    def create_user(self, payload: dict):
        return self.repo.insert(payload)"""

    base_meta = {
        "team": "backend",
        "system": "user-service",
        "version": "2.3.0",
        "last_updated": "2026-08-20T10:00:00",
        "security_level": "team",
        "page": 1,
    }

    docs = [
        Document(
            page_content=runbook_md,
            metadata={**base_meta, "source": "user-service-runbook.md", "doc_type": "runbook"},
        ),
        Document(
            page_content=python_code,
            metadata={**base_meta, "source": "user_service.py", "doc_type": "api"},
        ),
    ]

    chunks = split(docs)
    out_path = os.path.join(os.path.dirname(__file__), "_split_result.json")
    save_chunks_json(chunks, out_path)
    print(f"切分完成：{len(chunks)} 个 Chunk -> {out_path}")

    if os.environ.get("SKIP_INSERT", "1") != "1":
        try:
            count = insert(chunks)
            print(f"Milvus 入库成功：{count} 条")
        except Exception as exc:
            print(f"Milvus 入库失败：{exc}")
    else:
        print("跳过入库（设置 SKIP_INSERT=0 可启用）")


if __name__ == "__main__":
    main()
