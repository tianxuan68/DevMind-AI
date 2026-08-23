"""通用递归切分（非 Markdown / 非纯代码文档）。"""
from typing import List

from internal_kb_qa.core.models import Chunk, Document
from internal_kb_qa.text_splitters.chinese_recursive_splitter import ChineseRecursiveTextSplitter


class RecursiveSplitter:
    """对普通文本使用中文递归字符切分。"""

    def __init__(self, chunk_size: int = 1200, chunk_overlap: int = 150):
        self.splitter = ChineseRecursiveTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            keep_separator=True,
            is_separator_regex=True,
        )

    def split(self, documents: List[Document]) -> List[Chunk]:
        chunks: List[Chunk] = []
        for document in documents:
            pieces = self.splitter.split_text(document.page_content)
            if not pieces and document.page_content.strip():
                pieces = [document.page_content.strip()]
            for piece in pieces:
                meta = dict(document.metadata)
                meta.setdefault("chunk_type", "text")
                chunks.append(Chunk(text=piece, metadata=meta))
        return chunks
