"""代码块切分器：按类/函数边界切分，避免截断代码语义。"""
import ast
import re
from typing import Any, Dict, List, Optional, Tuple

from .models import Chunk, Document

_CODE_EXTENSIONS = {".py", ".java", ".go", ".js", ".ts", ".cpp", ".c", ".cs"}
_FENCED_CODE_RE = re.compile(r"```(\w*)\n(.*?)```", re.DOTALL)


def _language_from_source(source: str) -> str:
    lower = source.lower()
    for ext, lang in (
        (".py", "python"),
        (".java", "java"),
        (".go", "go"),
        (".js", "javascript"),
        (".ts", "typescript"),
        (".cpp", "cpp"),
        (".c", "c"),
        (".cs", "csharp"),
    ):
        if lower.endswith(ext):
            return lang
    return "text"


def _split_python_by_ast(source: str) -> List[str]:
    """按 Python 顶层类/函数边界切分。"""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return [source]

    lines = source.splitlines(keepends=True)
    boundaries: List[Tuple[int, int]] = []

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            start = node.lineno - 1
            end = node.end_lineno or node.lineno
            boundaries.append((start, end))

    if not boundaries:
        return [source]

    chunks: List[str] = []
    cursor = 0
    for start, end in boundaries:
        if start > cursor:
            prefix = "".join(lines[cursor:start]).strip()
            if prefix:
                chunks.append(prefix)
        block = "".join(lines[start:end]).strip()
        if block:
            chunks.append(block)
        cursor = end

    if cursor < len(lines):
        tail = "".join(lines[cursor:]).strip()
        if tail:
            chunks.append(tail)

    return chunks or [source]


class CodeSplitter:
    """按代码结构切分文档中的代码块或纯代码文件。"""

    def split(self, documents: List[Document]) -> List[Chunk]:
        chunks: List[Chunk] = []
        for document in documents:
            source = document.metadata.get("source", "")
            language = document.metadata.get("language") or _language_from_source(source)
            base_meta = dict(document.metadata)

            if language == "python" or str(source).lower().endswith(".py"):
                pieces = _split_python_by_ast(document.page_content)
            else:
                pieces = [document.page_content.strip()]

            for piece in pieces:
                if not piece.strip():
                    continue
                meta = dict(base_meta)
                meta["chunk_type"] = "code"
                meta["language"] = language
                chunks.append(Chunk(text=piece, metadata=meta))

        return chunks

    def extract_fenced_code_blocks(self, text: str) -> List[Tuple[str, str, str]]:
        """从 Markdown 中提取围栏代码块，返回 (language, code, full_block)。"""
        blocks: List[Tuple[str, str, str]] = []
        for match in _FENCED_CODE_RE.finditer(text):
            language = match.group(1) or "text"
            code = match.group(2).strip()
            blocks.append((language, code, match.group(0)))
        return blocks
