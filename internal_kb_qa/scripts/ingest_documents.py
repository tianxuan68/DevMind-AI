"""T3 文档入库脚本：解析 -> 切分 -> Embedding -> Milvus。"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

from langchain_core.documents import Document

from base.logger import logger
from internal_kb_qa.core.document_registry import sync_ingested_files
from internal_kb_qa.core.milvus_paths import canonical_storage_path
from internal_kb_qa.core.vector_store import VectorStore
from internal_kb_qa.document_loaders import load
from internal_kb_qa.text_splitters import split

SUPPORTED_SUFFIXES = {".md", ".markdown", ".pdf", ".docx", ".html", ".htm", ".json", ".txt"}
SKIP_FILENAMES = {"readme.md"}
FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    match = FRONTMATTER_RE.match(text)
    if not match:
        return {}, text
    meta: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        meta[key.strip()] = value.strip()
    body = text[match.end() :]
    return meta, body


def infer_source(path: Path, metadata: dict) -> str:
    for key in ("team", "category", "system"):
        value = metadata.get(key)
        if value:
            return value
    if path.suffix.lower() == ".pdf":
        return "backend"
    parent = path.parent.name.lower()
    if parent in {"infra", "backend", "frontend", "data", "ops", "hr"}:
        return parent
    return "ops"


def merge_pdf_pages(documents: list[Document], file_path: Path) -> list[Document]:
    if not documents:
        return []
    if len(documents) == 1:
        return documents
    merged = Document(
        page_content="\n\n".join(doc.page_content for doc in documents),
        metadata={
            **documents[0].metadata,
            "file_path": str(file_path),
            "pages": len(documents),
        },
    )
    return [merged]


def load_markdown(path: Path) -> list[Document]:
    raw = path.read_text(encoding="utf-8-sig")
    frontmatter, body = parse_frontmatter(raw)
    doc = Document(
        page_content=body.strip(),
        metadata={
            "source": infer_source(path, frontmatter),
            "file_path": canonical_storage_path(path),
            "doc_type": frontmatter.get("doc_type", "wiki"),
            "team": frontmatter.get("team"),
            "system": frontmatter.get("system"),
            "security_level": frontmatter.get("security_level"),
            "version": frontmatter.get("version"),
            "title": frontmatter.get("title", path.stem),
            "timestamp": frontmatter.get("last_updated", datetime.now().isoformat()),
        },
    )
    return [doc] if doc.page_content else []


def load_text_file(path: Path) -> list[Document]:
    raw = path.read_text(encoding="utf-8-sig")
    text = raw.strip()
    if not text:
        return []
    return [
        Document(
            page_content=text,
            metadata={
                "source": infer_source(path, {}),
                "file_path": canonical_storage_path(path),
                "doc_type": "wiki",
                "title": path.stem,
                "timestamp": datetime.now().isoformat(),
            },
        )
    ]


def load_file(path: Path) -> list[Document]:
    suffix = path.suffix.lower()
    if suffix in {".md", ".markdown"}:
        return load_markdown(path)
    if suffix == ".txt":
        return load_text_file(path)

    documents = load(str(path))
    if path.suffix.lower() == ".pdf":
        documents = merge_pdf_pages(documents, path)

    source = infer_source(path, {})
    canonical = canonical_storage_path(path)
    for doc in documents:
        doc.metadata["file_path"] = canonical
        doc.metadata["source"] = source
        doc.metadata.setdefault("timestamp", datetime.now().isoformat())
        doc.metadata.setdefault("title", path.stem)
    return documents


def _should_ingest(file_path: Path) -> bool:
    if file_path.suffix.lower() not in SUPPORTED_SUFFIXES:
        return False
    return file_path.name.lower() not in SKIP_FILENAMES


def collect_files(paths: list[Path]) -> list[Path]:
    files: list[Path] = []
    for path in paths:
        if path.is_file():
            if _should_ingest(path):
                files.append(path)
            continue
        if not path.is_dir():
            raise FileNotFoundError(f"路径不存在: {path}")
        for file_path in sorted(path.rglob("*")):
            if file_path.is_file() and _should_ingest(file_path):
                files.append(file_path)
    return files


def ingest_upload_file(
    file_path: Path,
    knowledge_base_id: int,
    doc_id: int,
    kb_name: str | None = None,
    kb_team: str | None = None,
    file_display_name: str | None = None,
    delete_existing: bool = True,
) -> dict:
    """知识库页面上传后的单文件入库：加载 → 父子切块 → 向量化写入 Milvus。"""
    if not file_path.exists():
        raise FileNotFoundError(f"文件不存在: {file_path}")

    suffix = file_path.suffix.lower()
    if suffix == ".doc":
        raise ValueError("不支持旧版 .doc，请转换为 .docx 后上传")
    if suffix not in SUPPORTED_SUFFIXES:
        raise ValueError(f"不支持的文件类型: {suffix}")

    store = VectorStore()
    if delete_existing:
        store.delete_by_storage_paths([str(file_path.resolve()), str(file_path)])

    documents = load_file(file_path)
    if not documents:
        raise ValueError("文档解析后无有效文本内容")

    for doc in documents:
        doc.metadata["knowledge_base_id"] = knowledge_base_id
        if kb_name:
            doc.metadata["knowledge_base"] = kb_name
            doc.metadata.setdefault("title", file_display_name or kb_name)
        if kb_team:
            doc.metadata["team"] = kb_team
            doc.metadata["source"] = kb_team
        if file_display_name:
            doc.metadata["title"] = file_display_name

    logger.info("上传入库: %s -> %s 段", file_path.name, len(documents))
    chunks = split(documents)
    if not chunks:
        raise ValueError("切块后无有效子块")
    logger.info("切块完成: %s 子块", len(chunks))

    inserted = store.insert(chunks)
    _update_document_chunk_count(doc_id, len(chunks))

    return {
        "files": 1,
        "documents": len(documents),
        "chunks": len(chunks),
        "inserted": inserted,
        "milvus_rows": store.count(),
    }


def ingest_paths(
    paths: list[Path],
    recreate: bool = False,
    sync_mysql: bool = True,
    knowledge_base_id: int | None = None,
    doc_id: int | None = None,
    delete_existing: bool = True,
) -> dict:
    """解析、切块并写入 Milvus；可选同步 MySQL。"""
    files = collect_files(paths)
    if not files:
        raise RuntimeError("未找到可入库的文档")

    store = VectorStore()
    if recreate:
        store.drop_collection()
        store = VectorStore()

    all_documents: list[Document] = []
    file_metadata: dict[str, dict] = {}
    for file_path in files:
        if delete_existing:
            store.delete_by_storage_paths([str(file_path.resolve()), str(file_path)])
        docs = load_file(file_path)
        logger.info("加载文档: %s -> %s 段", file_path, len(docs))
        all_documents.extend(docs)
        if docs:
            file_metadata[str(file_path.resolve())] = dict(docs[0].metadata)

    logger.info("开始切分，共 %s 个原始文档", len(all_documents))
    chunks = split(all_documents)
    logger.info("切分完成，子块数量: %s", len(chunks))

    inserted = store.insert(chunks)

    mysql_sync = {"synced": 0, "files": 0}
    if sync_mysql:
        mysql_sync = sync_ingested_files(files, chunks, file_metadata)
    elif doc_id and knowledge_base_id:
        _update_document_chunk_count(doc_id, len(chunks))

    return {
        "files": len(files),
        "documents": len(all_documents),
        "chunks": len(chunks),
        "inserted": inserted,
        "milvus_rows": store.count(),
        "mysql_synced": mysql_sync.get("synced", 0),
    }


def _update_document_chunk_count(doc_id: int, chunk_count: int) -> None:
    import pymysql
    from base.config import Config

    conf = Config()
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
            cur.execute(
                "UPDATE documents SET chunk_count=%s, index_status='indexed' WHERE id=%s",
                (chunk_count, doc_id),
            )
    finally:
        conn.close()


def ingest(paths: list[Path], recreate: bool = False, sync_mysql: bool = True) -> dict:
    return ingest_paths(paths, recreate=recreate, sync_mysql=sync_mysql, delete_existing=not recreate)


def main() -> int:
    parser = argparse.ArgumentParser(description="解析文档并写入 Milvus 向量库")
    parser.add_argument(
        "--dir",
        action="append",
        dest="dirs",
        help="待入库目录，可重复指定",
    )
    parser.add_argument(
        "--file",
        action="append",
        dest="files",
        help="待入库文件，可重复指定",
    )
    parser.add_argument(
        "--recreate",
        action="store_true",
        help="删除并重建 Milvus 集合后再写入",
    )
    parser.add_argument(
        "--no-sync-mysql",
        action="store_true",
        help="仅写入 Milvus，不同步 MySQL documents 表",
    )
    args = parser.parse_args()

    paths: list[Path] = []
    for value in args.dirs or []:
        paths.append(Path(value))
    for value in args.files or []:
        paths.append(Path(value))
    if not paths:
        parser.error("请至少指定一个 --dir 或 --file")

    try:
        result = ingest(paths, recreate=args.recreate, sync_mysql=not args.no_sync_mysql)
    except Exception as exc:
        logger.exception("入库失败: %s", exc)
        return 1

    print(
        f"[OK] 入库完成: files={result['files']} documents={result['documents']} "
        f"chunks={result['chunks']} inserted={result['inserted']} milvus_rows={result['milvus_rows']} "
        f"mysql_synced={result['mysql_synced']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
