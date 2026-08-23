"""T3 基线参考目录（兼容层）。

正式实现已迁移至 internal_kb_qa：
- 切分：internal_kb_qa/text_splitters/
- 入库：internal_kb_qa/core/vector_store.py
- 入库脚本：internal_kb_qa/scripts/ingest_documents.py
"""
from internal_kb_qa.core.models import Chunk, Document, document_from_langchain
from internal_kb_qa.core.vector_store import VectorStore, insert
from internal_kb_qa.text_splitters import (
    CodeSplitter,
    MarkdownHeaderSplitter,
    RecursiveSplitter,
    save_chunks_json,
    split,
)

__all__ = [
    "split",
    "insert",
    "save_chunks_json",
    "Chunk",
    "Document",
    "document_from_langchain",
    "VectorStore",
    "CodeSplitter",
    "MarkdownHeaderSplitter",
    "RecursiveSplitter",
]
