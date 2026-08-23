"""T3 文档切分器。

对外接口（任务分工 T3 契约）：
    split(documents: list[Document]) -> list[Chunk]
"""
import json
import logging
from typing import Any, List, Sequence

from internal_kb_qa.core.models import Chunk, Document, document_from_langchain
from internal_kb_qa.core.vector_store import VectorStore, insert
from internal_kb_qa.text_splitters.code_splitter import CODE_EXTENSIONS, CodeSplitter, language_from_source
from internal_kb_qa.text_splitters.markdown_splitter import MarkdownHeaderSplitter
from internal_kb_qa.text_splitters.recursive_splitter import RecursiveSplitter

__all__ = [
    "split",
    "insert",
    "save_chunks_json",
    "Chunk",
    "Document",
    "VectorStore",
    "CodeSplitter",
    "MarkdownHeaderSplitter",
    "RecursiveSplitter",
]

logger = logging.getLogger(__name__)

_DEFAULT_CHUNK_SIZE = 1200
_DEFAULT_CHUNK_OVERLAP = 150


def _load_retrieval_config() -> tuple[int, int]:
    try:
        from internal_kb_qa.core.vector_store import _load_config

        config = _load_config()
        return config.CHUNK_SIZE, config.CHUNK_OVERLAP
    except Exception:
        return _DEFAULT_CHUNK_SIZE, _DEFAULT_CHUNK_OVERLAP


def _normalize_documents(documents: Sequence[Any]) -> List[Document]:
    normalized: List[Document] = []
    for item in documents:
        if isinstance(item, dict):
            normalized.append(
                Document(
                    page_content=item.get("page_content") or item.get("text", ""),
                    metadata=dict(item.get("metadata") or {}),
                )
            )
        else:
            normalized.append(document_from_langchain(item))
    return normalized


def _is_code_document(document: Document) -> bool:
    source = str(document.metadata.get("source", "")).lower()
    doc_type = str(document.metadata.get("doc_type", "")).lower()
    if document.metadata.get("language"):
        return True
    if doc_type in {"api", "code"}:
        return True
    return any(source.endswith(ext) for ext in CODE_EXTENSIONS)


def _is_markdown_document(document: Document) -> bool:
    source = str(document.metadata.get("source", "")).lower()
    doc_type = str(document.metadata.get("doc_type", "")).lower()
    if source.endswith(".md") or doc_type in {"runbook", "wiki", "markdown"}:
        return True
    content = document.page_content
    return "#" in content and ("\n##" in content or content.strip().startswith("#"))


def _enrich_metadata(document: Document) -> Document:
    meta = dict(document.metadata)
    source = str(meta.get("source", ""))
    meta.setdefault("source", source or "unknown")
    meta.setdefault("page", 1)
    meta.setdefault("doc_type", "report")
    meta.setdefault("team", "unknown")
    meta.setdefault("system", "unknown")
    meta.setdefault("version", "0.0.0")
    meta.setdefault("last_updated", "")
    meta.setdefault("security_level", "team")
    if _is_code_document(document) and "language" not in meta:
        meta["language"] = language_from_source(source)
    document.metadata = meta
    return document


def split(documents: Sequence[Any]) -> List[Chunk]:
    """将 T2 输出的 Document 列表切分为 Chunk 列表。"""
    chunk_size, chunk_overlap = _load_retrieval_config()
    markdown_splitter = MarkdownHeaderSplitter(chunk_size, chunk_overlap)
    code_splitter = CodeSplitter()
    recursive_splitter = RecursiveSplitter(chunk_size, chunk_overlap)

    all_chunks: List[Chunk] = []
    for raw in _normalize_documents(documents):
        document = _enrich_metadata(raw)
        if _is_code_document(document) and not _is_markdown_document(document):
            pieces = code_splitter.split([document])
        elif _is_markdown_document(document):
            pieces = markdown_splitter.split([document])
        else:
            pieces = recursive_splitter.split([document])
        all_chunks.extend(pieces)

    logger.info("split() 完成：%d 个 Document -> %d 个 Chunk", len(documents), len(all_chunks))
    return all_chunks


def save_chunks_json(chunks: Sequence[Chunk], path: str) -> None:
    """将切分结果保存为 JSON（便于联调与验收）。"""
    payload = [chunk.to_dict() for chunk in chunks]
    with open(path, "w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)
