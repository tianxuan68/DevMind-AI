"""Markdown 标题层级切分 + 代码块独立抽取。"""
import re
from typing import Any, Dict, List, Optional, Tuple

from .code_splitter import CodeSplitter
from .edu_chinese_recursive_text_splitter import ChineseRecursiveTextSplitter
from .models import Chunk, Document

_HEADER_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_FENCED_CODE_RE = re.compile(r"```(\w*)\n(.*?)```", re.DOTALL)


def _normalize_headers(headers: Dict[int, Optional[str]]) -> Dict[str, Optional[str]]:
    return {
        "header_1": headers.get(1),
        "header_2": headers.get(2),
        "header_3": headers.get(3),
        "header_4": headers.get(4),
        "header_5": headers.get(5),
        "header_6": headers.get(6),
    }


class MarkdownHeaderSplitter:
    """按 Markdown 标题层级切分，并将围栏代码块单独成块。"""

    def __init__(self, chunk_size: int = 1200, chunk_overlap: int = 150):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.code_splitter = CodeSplitter()
        self.text_splitter = ChineseRecursiveTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            keep_separator=True,
            is_separator_regex=True,
        )

    def split(self, documents: List[Document]) -> List[Chunk]:
        chunks: List[Chunk] = []
        for document in documents:
            chunks.extend(self._split_document(document))
        return chunks

    def _split_document(self, document: Document) -> List[Chunk]:
        text = document.page_content.replace("\r\n", "\n")
        base_meta = dict(document.metadata)
        sections = self._split_by_headers(text)
        chunks: List[Chunk] = []

        for section_text, headers in sections:
            section_text = section_text.strip()
            if not section_text:
                continue

            code_blocks = self.code_splitter.extract_fenced_code_blocks(section_text)
            prose_text = section_text
            for _, _, full_block in code_blocks:
                prose_text = prose_text.replace(full_block, "\n")

            header_meta = _normalize_headers(headers)
            prose_text = prose_text.strip()
            if prose_text:
                sub_pieces = self.text_splitter.split_text(prose_text)
                if not sub_pieces:
                    sub_pieces = [prose_text]
                for piece in sub_pieces:
                    meta = dict(base_meta)
                    meta["chunk_type"] = "text"
                    meta.update({k: v for k, v in header_meta.items() if v})
                    chunks.append(Chunk(text=piece, metadata=meta))

            for language, code, full_block in code_blocks:
                if not code.strip():
                    continue
                meta = dict(base_meta)
                meta["chunk_type"] = "code"
                meta["language"] = language or "text"
                meta.update({k: v for k, v in header_meta.items() if v})
                chunks.append(Chunk(text=full_block.strip(), metadata=meta))

        return chunks

    def _split_by_headers(self, text: str) -> List[Tuple[str, Dict[int, Optional[str]]]]:
        lines = text.split("\n")
        headers: Dict[int, Optional[str]] = {level: None for level in range(1, 7)}
        sections: List[Tuple[str, Dict[int, Optional[str]]]] = []
        current_lines: List[str] = []

        def flush() -> None:
            if current_lines:
                sections.append(("\n".join(current_lines), dict(headers)))

        for line in lines:
            match = _HEADER_RE.match(line)
            if match:
                flush()
                current_lines = [line]
                level = len(match.group(1))
                title = match.group(2).strip()
                headers[level] = title
                for deeper in range(level + 1, 7):
                    headers[deeper] = None
            else:
                current_lines.append(line)

        flush()
        if not sections:
            sections.append((text, dict(headers)))
        return sections
