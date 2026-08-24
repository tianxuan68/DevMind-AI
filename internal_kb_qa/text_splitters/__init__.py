"""T3 文档切分器：父块 + 子块分层切分。"""
from __future__ import annotations

from datetime import datetime

from langchain_core.documents import Document
from langchain_text_splitters import MarkdownTextSplitter

from base.config import Config
from internal_kb_qa.text_splitters.chinese_recursive_splitter import ChineseRecursiveTextSplitter

__all__ = ["split", "RecursiveSplitter", "CodeSplitter"]


class RecursiveSplitter:
    def split(self, documents: list[Document]) -> list[Document]:
        return split(documents)


class CodeSplitter:
    def split(self, documents: list[Document]) -> list[Document]:
        raise NotImplementedError("CodeSplitter is not implemented yet")


def split(documents: list[Document]) -> list[Document]:
    """将文档切分为子块，并写入 parent_id / parent_content 元数据。"""
    conf = Config()
    parent_size = conf.PARENT_CHUNK_SIZE
    child_size = conf.CHILD_CHUNK_SIZE
    overlap = conf.CHUNK_OVERLAP

    parent_splitter = ChineseRecursiveTextSplitter(chunk_size=parent_size, chunk_overlap=overlap)
    child_splitter = ChineseRecursiveTextSplitter(chunk_size=child_size, chunk_overlap=overlap)
    markdown_parent = MarkdownTextSplitter(chunk_size=parent_size, chunk_overlap=overlap)
    markdown_child = MarkdownTextSplitter(chunk_size=child_size, chunk_overlap=overlap)

    child_chunks: list[Document] = []
    for doc_index, doc in enumerate(documents):
        file_path = doc.metadata.get("file_path", "")
        is_markdown = str(file_path).lower().endswith((".md", ".markdown"))
        parent_tool = markdown_parent if is_markdown else parent_splitter
        child_tool = markdown_child if is_markdown else child_splitter

        parent_docs = parent_tool.split_documents([doc])
        for parent_index, parent_doc in enumerate(parent_docs):
            parent_id = f"doc_{doc_index}_parent_{parent_index}"
            sub_chunks = child_tool.split_documents([parent_doc])
            for child_index, sub_chunk in enumerate(sub_chunks):
                sub_chunk.metadata["parent_id"] = parent_id
                sub_chunk.metadata["parent_content"] = parent_doc.page_content
                sub_chunk.metadata["id"] = f"{parent_id}_child_{child_index}"
                if "timestamp" not in sub_chunk.metadata:
                    sub_chunk.metadata["timestamp"] = datetime.now().isoformat()
                child_chunks.append(sub_chunk)
    return child_chunks
