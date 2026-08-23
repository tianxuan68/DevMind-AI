"""T8 响应模型：Source、QueryResponse、FeedbackResponse、WS 流式消息。

契约基准：docs/api/接口文档.md（T8 契约先行定稿）。
"""
from pydantic import BaseModel


class Source(BaseModel):
    """回答引用出处。"""

    title: str
    page: int | None = None
    score: float
    text: str


class QueryResponse(BaseModel):
    answer: str
    is_streaming: bool
    need_human: bool
    sources: list[Source] = []
    session_id: str
    processing_time: float


class FeedbackResponse(BaseModel):
    status: str
    ticket_id: str | None = None


class StreamMessage(BaseModel):
    """WS /api/stream 服务端下发的消息基类，type 为判别字段。"""

    type: str


class StreamStart(StreamMessage):
    type: str = "start"
    session_id: str


class StreamToken(StreamMessage):
    type: str = "token"
    token: str


class StreamEnd(StreamMessage):
    type: str = "end"
    is_complete: bool
    sources: list[Source] = []
    processing_time: float


class StreamError(StreamMessage):
    type: str = "error"
    error: str
