"""T3 本地调试入口：切分演示 + 可选 Milvus 入库。

用法（在项目根目录 D:\\DevMindai 下）：
    .venv\\Scripts\\python.exe -m rag_qa.edu_text_spliter.run_demo
"""
import logging
import os
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from rag_qa.edu_text_spliter import Document, insert, save_chunks_json, split


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
            metadata={
                **base_meta,
                "source": "user-service-runbook.md",
                "doc_type": "runbook",
            },
        ),
        Document(
            page_content=python_code,
            metadata={
                **base_meta,
                "source": "user_service.py",
                "doc_type": "api",
            },
        ),
    ]

    chunks = split(docs)
    out_path = os.path.join(os.path.dirname(__file__), "_split_result.json")
    save_chunks_json(chunks, out_path)
    print(f"切分完成：{len(chunks)} 个 Chunk -> {out_path}")

    for index, chunk in enumerate(chunks, 1):
        preview = chunk.text.replace("\n", " ")[:80]
        print(f"  [{index}] type={chunk.metadata.get('chunk_type')} preview={preview}...")

    try:
        count = insert(chunks)
        print(f"Milvus 入库成功：{count} 条")
    except Exception as exc:
        print(f"Milvus 入库跳过（需启动 Milvus + BGE-M3 模型）：{exc}")


if __name__ == "__main__":
    main()
