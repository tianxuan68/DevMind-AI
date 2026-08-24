"""独立进程执行向量检索，避免模型 OOM 拖垮 API 主进程。

用法：
    echo '{"queries":["Milvus"],"top_k":5,"mode":"hybrid","use_rerank":false}' | python -m internal_kb_qa.scripts.retrieval_worker
"""
from __future__ import annotations

import json
import os
import sys

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")


def _configure_worker_logging() -> None:
    import logging

    root = logging.getLogger()
    for handler in root.handlers[:]:
        root.removeHandler(handler)
    root.addHandler(logging.StreamHandler(sys.stderr))


def _extract_json_payload(stdout: bytes) -> dict | None:
    text = (stdout or b"").decode("utf-8", errors="replace")
    for line in reversed(text.splitlines()):
        line = line.strip()
        if line.startswith("{"):
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue
    return None


def main() -> int:
    _configure_worker_logging()
    try:
        raw = sys.stdin.buffer.read()
        payload = json.loads(raw.decode("utf-8"))
        from internal_kb_qa.core.hybrid_search import search

        all_hits = []
        file_paths = payload.get("file_paths")
        filter_payload = {"file_paths": file_paths} if file_paths else None
        for query_text in payload.get("queries") or []:
            if not isinstance(query_text, str) or not query_text.strip():
                continue
            hits = search(
                query_text.strip(),
                top_k=int(payload.get("top_k", 5)),
                filter=filter_payload,
                mode=payload.get("mode", "hybrid"),
                use_rerank=bool(payload.get("use_rerank", False)),
            )
            all_hits.extend(hits)

        out = {
            "ok": True,
            "hits": [(hit.text, hit.score, hit.metadata or {}) for hit in all_hits],
        }
        sys.stdout.write(json.dumps(out, ensure_ascii=False))
        sys.stdout.flush()
        return 0
    except Exception as exc:
        sys.stdout.write(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        sys.stdout.flush()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
