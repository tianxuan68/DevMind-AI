"""按文件路径从 Milvus 查询切块（不加载 Embedding 模型）。"""
from __future__ import annotations

from pathlib import Path

from pymilvus import MilvusClient

from base.config import Config
from base.logger import logger

conf = Config()

OUTPUT_FIELDS = ["id", "text", "parent_id", "parent_content", "source", "timestamp", "file_path", "title"]


def _escape_filter_value(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _candidate_paths(file_path: str) -> list[str]:
    resolved = Path(file_path).resolve()
    candidates = [
        str(resolved),
        str(resolved).replace("\\", "/"),
        file_path,
        file_path.replace("\\", "/"),
    ]

    for parent in [Path.cwd().resolve(), *resolved.parents]:
        if (parent / "config.ini").exists() or (parent / "pyproject.toml").exists():
            try:
                rel = resolved.relative_to(parent)
                candidates.append(str(rel))
                candidates.append(str(rel).replace("\\", "/"))
                candidates.append(str(rel).replace("/", "\\"))
            except ValueError:
                pass

    seen: set[str] = set()
    ordered: list[str] = []
    for item in candidates:
        if item and item not in seen:
            seen.add(item)
            ordered.append(item)
    return ordered


def _query_by_filename(client: MilvusClient, file_name: str, limit: int) -> list[dict]:
    if not file_name:
        return []
    escaped = _escape_filter_value(file_name)
    expr = f'file_path like "%{escaped}"'
    try:
        return client.query(
            collection_name=conf.MILVUS_COLLECTION_NAME,
            filter=expr,
            output_fields=OUTPUT_FIELDS,
            limit=limit,
        )
    except Exception as exc:
        logger.warning("Milvus 按文件名查询失败 name=%s: %s", file_name, exc)
        return []


def query_chunks_by_file_path(file_path: str, limit: int = 2000) -> list[dict]:
    """按 storage_path 查询 Milvus 中该文档的全部子块。"""
    if not file_path:
        return []

    client = MilvusClient(uri=f"http://{conf.MILVUS_HOST}:{conf.MILVUS_PORT}", db_name=conf.MILVUS_DATABASE_NAME)
    if not client.has_collection(conf.MILVUS_COLLECTION_NAME):
        return []

    client.load_collection(conf.MILVUS_COLLECTION_NAME)

    for candidate in _candidate_paths(file_path):
        expr = f'file_path == "{_escape_filter_value(candidate)}"'
        try:
            rows = client.query(
                collection_name=conf.MILVUS_COLLECTION_NAME,
                filter=expr,
                output_fields=OUTPUT_FIELDS,
                limit=limit,
            )
        except Exception as exc:
            logger.warning("Milvus 切块查询失败 path=%s: %s", candidate, exc)
            continue
        if rows:
            logger.info("命中切块 path=%s count=%s", candidate, len(rows))
            return rows

    file_name = Path(file_path).name
    rows = _query_by_filename(client, file_name, limit)
    if rows:
        exact = [row for row in rows if Path(str(row.get("file_path") or "")).name == file_name]
        if exact:
            logger.info("按文件名精确命中切块 name=%s count=%s", file_name, len(exact))
            return exact
        logger.info("按文件名模糊命中切块 name=%s count=%s", file_name, len(rows))
    return rows


def group_chunks(rows: list[dict]) -> list[dict]:
    """按 parent_id 分组，便于前端展示父块-子块结构。"""
    parents: dict[str, dict] = {}
    order: list[str] = []

    for row in rows:
        parent_id = row.get("parent_id") or row.get("id") or "unknown"
        if parent_id not in parents:
            parents[parent_id] = {
                "parentId": parent_id,
                "parentContent": row.get("parent_content") or "",
                "source": row.get("source"),
                "chunks": [],
            }
            order.append(parent_id)

        text = row.get("text") or ""
        parents[parent_id]["chunks"].append(
            {
                "id": row.get("id"),
                "text": text,
                "charCount": len(text),
                "source": row.get("source"),
                "timestamp": row.get("timestamp"),
            }
        )

    for parent in parents.values():
        parent["chunks"].sort(key=lambda item: item.get("id") or "")

    return [parents[pid] for pid in order]
