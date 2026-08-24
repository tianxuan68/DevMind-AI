"""将 ingest 结果同步到 MySQL documents 表，供知识库管理页展示。"""
from __future__ import annotations

import mimetypes
from collections import Counter
from datetime import datetime
from pathlib import Path

import pymysql
from langchain_core.documents import Document

from base.config import Config
from base.logger import logger

KB_NAME_TO_ID = {
    "平台工程知识库": 1,
    "安全与合规知识库": 2,
    "研发实践知识库": 3,
}

RAW_DIR_TO_KB_ID = {
    "platform": 1,
    "security": 2,
    "backend": 3,
}

RAG_SEED_TO_KB_ID = {
    "access_request.md": 2,
    "policy_general.md": 2,
    "tech.md": 3,
    "incident.md": 1,
    "common.md": 1,
    "ticket_inquiry.md": 1,
    "complaint_suggestion.md": 1,
}

DEFAULT_KB_ID = 1
DEFAULT_CREATED_BY = 1


def resolve_knowledge_base_id(file_path: Path, metadata: dict | None = None) -> int:
    """根据路径/frontmatter 推断所属知识库 ID。"""
    metadata = metadata or {}
    kb_name = metadata.get("knowledge_base")
    if kb_name and kb_name in KB_NAME_TO_ID:
        return KB_NAME_TO_ID[kb_name]

    parts = {part.lower() for part in file_path.parts}
    for folder, kb_id in RAW_DIR_TO_KB_ID.items():
        if folder in parts:
            return kb_id

    if "rag_seed" in parts:
        mapped = RAG_SEED_TO_KB_ID.get(file_path.name.lower())
        if mapped:
            return mapped

    if file_path.suffix.lower() == ".pdf":
        return 3

    logger.warning("未匹配知识库目录，默认归入平台工程知识库: %s", file_path)
    return DEFAULT_KB_ID


def _infer_doc_type(file_path: Path, metadata: dict) -> str:
    doc_type = metadata.get("doc_type")
    if doc_type:
        return doc_type
    suffix = file_path.suffix.lower()
    if suffix == ".pdf":
        return "report"
    if suffix in {".md", ".markdown"}:
        return "wiki"
    return suffix.lstrip(".") or "wiki"


def _parse_last_updated(metadata: dict) -> datetime | None:
    raw = metadata.get("timestamp") or metadata.get("last_updated")
    if not raw:
        return None
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00").split("+")[0])
    except ValueError:
        return None


def _chunk_counts_by_file(chunks: list[Document]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for chunk in chunks:
        file_path = chunk.metadata.get("file_path")
        if not file_path:
            continue
        counts[str(Path(file_path).resolve())] += 1
    return counts


def sync_ingested_files(
    files: list[Path],
    chunks: list[Document],
    file_metadata: dict[str, dict] | None = None,
    created_by: int = DEFAULT_CREATED_BY,
) -> dict:
    """按 ingest 文件写入/更新 MySQL documents 记录。"""
    conf = Config()
    file_metadata = file_metadata or {}
    chunk_counts = _chunk_counts_by_file(chunks)
    synced = 0

    conn = pymysql.connect(
        host=conf.MYSQL_HOST,
        user=conf.MYSQL_USER,
        password=conf.MYSQL_PASSWORD,
        database=conf.MYSQL_DATABASE,
        charset="utf8mb4",
        autocommit=True,
    )
    try:
        with conn.cursor() as cur:
            for file_path in files:
                resolved = str(file_path.resolve())
                metadata = file_metadata.get(resolved, {})
                kb_id = resolve_knowledge_base_id(file_path, metadata)
                doc_type = _infer_doc_type(file_path, metadata)
                mime_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
                size_bytes = file_path.stat().st_size if file_path.exists() else 0
                chunk_count = chunk_counts.get(resolved, 0)
                last_updated = _parse_last_updated(metadata)

                cur.execute(
                    """
                    INSERT INTO documents (
                        knowledge_base_id, file_name, size_bytes, mime_type, storage_path,
                        created_by, index_status, doc_source, doc_type, team, system_name,
                        version, security_level, status, chunk_count, last_updated
                    ) VALUES (
                        %s, %s, %s, %s, %s,
                        %s, 'indexed', %s, %s, %s, %s,
                        %s, %s, 'active', %s, %s
                    )
                    ON DUPLICATE KEY UPDATE
                        knowledge_base_id = VALUES(knowledge_base_id),
                        file_name = VALUES(file_name),
                        size_bytes = VALUES(size_bytes),
                        mime_type = VALUES(mime_type),
                        storage_path = VALUES(storage_path),
                        index_status = 'indexed',
                        team = VALUES(team),
                        system_name = VALUES(system_name),
                        version = VALUES(version),
                        security_level = VALUES(security_level),
                        chunk_count = VALUES(chunk_count),
                        last_updated = VALUES(last_updated),
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (
                        kb_id,
                        file_path.name,
                        size_bytes,
                        mime_type,
                        resolved,
                        created_by,
                        resolved,
                        doc_type,
                        metadata.get("team"),
                        metadata.get("system"),
                        metadata.get("version"),
                        metadata.get("security_level") or "team",
                        chunk_count,
                        last_updated,
                    ),
                )
                synced += 1
                logger.info(
                    "已同步 MySQL 文档: %s -> kb=%s chunks=%s",
                    file_path.name,
                    kb_id,
                    chunk_count,
                )
    finally:
        conn.close()

    return {"synced": synced, "files": len(files)}
