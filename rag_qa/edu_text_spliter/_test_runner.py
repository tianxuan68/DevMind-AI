"""临时测试脚本，运行后输出到 _test_output.txt"""
import json
import os
import sys
import traceback

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
OUT = os.path.join(os.path.dirname(__file__), "_test_output.txt")
sys.path.insert(0, PROJECT_ROOT)

lines = []


def log(msg: str) -> None:
    lines.append(msg)
    print(msg)


def main() -> int:
    try:
        from rag_qa.edu_text_spliter import Document, insert, split, save_chunks_json
        from rag_qa.edu_text_spliter.edu_chinese_recursive_text_splitter import ChineseRecursiveTextSplitter

        log("=== TEST 1: import ===")
        log("PASS: all imports ok")

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

        docs = [
            Document(
                page_content=runbook,
                metadata={**base, "source": "user-service-runbook.md", "doc_type": "runbook"},
            ),
            Document(
                page_content=python_code,
                metadata={**base, "source": "user_service.py", "doc_type": "api"},
            ),
        ]

        log("=== TEST 2: split demo docs ===")
        chunks = split(docs)
        log(f"PASS: split produced {len(chunks)} chunks")

        required = [
            "team", "system", "version", "last_updated", "security_level",
            "source", "page", "doc_type", "chunk_type",
        ]
        for i, chunk in enumerate(chunks):
            missing = [k for k in required if k not in chunk.metadata]
            if missing:
                log(f"FAIL: chunk {i} missing metadata: {missing}")
                return 1
            log(f"  chunk[{i}] type={chunk.metadata['chunk_type']} len={len(chunk.text)} source={chunk.metadata['source']}")

        code_chunks = [c for c in chunks if c.metadata["chunk_type"] == "code"]
        text_chunks = [c for c in chunks if c.metadata["chunk_type"] == "text"]
        log(f"PASS: text={len(text_chunks)} code={len(code_chunks)}")

        if len(code_chunks) < 1:
            log("FAIL: expected at least 1 code chunk")
            return 1

        header_chunks = [c for c in chunks if c.metadata.get("header_1") or c.metadata.get("header_2")]
        if not header_chunks:
            log("FAIL: expected markdown header metadata")
            return 1
        log(f"PASS: {len(header_chunks)} chunks have header metadata")

        out_path = os.path.join(os.path.dirname(__file__), "_split_result.json")
        save_chunks_json(chunks, out_path)
        log(f"PASS: saved {out_path}")

        log("=== TEST 3: chinese recursive splitter ===")
        cs = ChineseRecursiveTextSplitter(chunk_size=50, chunk_overlap=5)
        parts = cs.split_text("第一句。第二句很长很长很长很长很长很长很长很长很长很长。第三句。")
        if not parts:
            log("FAIL: chinese splitter returned empty")
            return 1
        log(f"PASS: chinese splitter {len(parts)} parts")

        log("=== TEST 4: plain text split ===")
        plain = Document(
            page_content="这是一段普通中文文本。没有标题。第二句内容。",
            metadata={**base, "source": "plain.txt", "doc_type": "report"},
        )
        plain_chunks = split([plain])
        if not plain_chunks:
            log("FAIL: plain text split empty")
            return 1
        log(f"PASS: plain text {len(plain_chunks)} chunks")

        log("=== TEST 5: milvus insert (optional, SKIP_INSERT=1 to skip) ===")
        if os.environ.get("SKIP_INSERT", "1") == "1":
            log("SKIP: insert test disabled (set SKIP_INSERT=0 to enable)")
        else:
            try:
                count = insert(chunks)
                log(f"PASS: milvus insert {count} rows")
            except Exception as exc:
                log(f"SKIP/FAIL: milvus insert: {exc}")

        log("=== ALL CORE TESTS PASSED ===")
        return 0

    except Exception:
        log("FAIL: unexpected error")
        log(traceback.format_exc())
        return 1


if __name__ == "__main__":
    code = main()
    try:
        with open(OUT, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
    except OSError:
        pass
    sys.exit(code)
