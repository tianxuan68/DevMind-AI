"""T8 请求模型：QueryRequest、StreamRequest、FeedbackRequest、AuthMessage。

契约基准：docs/api/接口文档.md（T8 契约先行定稿）。
"""
from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    query: str
    session_id: str | None = None
    source_filter: str | None = None


class StreamRequest(BaseModel):
    """WS /api/stream 客户端发送的查询消息（type=query）。"""

    type: str = "query"
    query: str
    session_id: str | None = None
    source_filter: str | None = None


class AuthMessage(BaseModel):
    """WS /api/stream 首条认证消息（type=auth）。"""

    type: str = "auth"
    token: str


class FeedbackRequest(BaseModel):
    session_id: str
    query: str
    rating: int = Field(ge=1, le=5)
    comment: str | None = None
    need_human: bool | None = False
