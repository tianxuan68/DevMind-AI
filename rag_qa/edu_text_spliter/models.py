"""T3 数据模型：Document（T2 输出）与 Chunk（切分结果）。"""
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class Document:
    """T2 解析器输出的标准文档对象。"""

    page_content: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Chunk:
    """切分后的文本块，供向量化入库使用。"""

    text: str
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {"text": self.text, "metadata": self.metadata}


def document_from_langchain(doc) -> Document:
    """兼容 LangChain Document 对象。"""
    if isinstance(doc, Document):
        return doc
    return Document(
        page_content=doc.page_content,
        metadata=dict(doc.metadata or {}),
    )
