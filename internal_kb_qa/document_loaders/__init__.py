"""T2 多格式文档解析器。

统一对外接口（任务分工 T2 契约）：
    load(file_path: str) -> list[Document]

支持的内部文档格式：
- Confluence / Wiki 导出 HTML
- Word (.docx)
- Markdown (.md)
- PDF (.pdf)
- OpenAPI / Swagger JSON
"""
from .confluence_loader import ConfluenceLoader
from .markdown_loader import MarkdownLoader
from .openapi_loader import OpenAPILoader
from .pdf_loader import PDFLoader
from .word_loader import WordLoader

__all__ = [
    "load",
    "ConfluenceLoader",
    "MarkdownLoader",
    "OpenAPILoader",
    "PDFLoader",
    "WordLoader",
]


def load(file_path: str):
    """按扩展名分发到对应 loader，返回 Document 列表。"""
    raise NotImplementedError("TODO(T2 数据组): implement load() dispatch")
