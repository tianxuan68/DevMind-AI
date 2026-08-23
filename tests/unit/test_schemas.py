# -*- coding: utf-8 -*-
"""请求/响应模型契约测试：字段、约束、WS 消息判别。"""
import pytest
from pydantic import ValidationError

from internal_kb_qa.api.schemas.request import (
    AuthMessage,
    FeedbackRequest,
    QueryRequest,
    StreamRequest,
)
from internal_kb_qa.api.schemas.response import (
    QueryResponse,
    Source,
    StreamEnd,
    StreamError,
    StreamStart,
    StreamToken,
)


class TestQueryRequest:
    def test_optional_fields_default_none(self):
        req = QueryRequest(query="问题")
        assert req.session_id is None
        assert req.source_filter is None

    def test_query_required(self):
        with pytest.raises(ValidationError):
            QueryRequest()


class TestFeedbackRequest:
    @pytest.mark.parametrize("rating", [1, 3, 5])
    def test_rating_in_range(self, rating):
        req = FeedbackRequest(session_id="s1", query="q", rating=rating)
        assert req.rating == rating

    @pytest.mark.parametrize("rating", [0, 6, -1])
    def test_rating_out_of_range(self, rating):
        with pytest.raises(ValidationError):
            FeedbackRequest(session_id="s1", query="q", rating=rating)

    def test_need_human_default_false(self):
        req = FeedbackRequest(session_id="s1", query="q", rating=4)
        assert req.need_human is False

    def test_comment_optional(self):
        req = FeedbackRequest(session_id="s1", query="q", rating=4, comment="很好")
        assert req.comment == "很好"


class TestStreamMessages:
    def test_stream_request_default_type(self):
        msg = StreamRequest(query="q")
        assert msg.type == "query"

    def test_auth_message(self):
        msg = AuthMessage(token="tk")
        assert msg.type == "auth"

    def test_stream_start_fields(self):
        msg = StreamStart(session_id="s1")
        assert msg.type == "start"
        assert msg.session_id == "s1"

    def test_stream_token_fields(self):
        msg = StreamToken(token="片段")
        assert msg.type == "token"

    def test_stream_end_sources_default_empty(self):
        msg = StreamEnd(is_complete=True, processing_time=1.2)
        assert msg.sources == []

    def test_stream_error_fields(self):
        msg = StreamError(error="出错了")
        assert msg.type == "error"


class TestSource:
    def test_page_optional(self):
        src = Source(title="文档.md", score=0.9, text="片段")
        assert src.page is None

    def test_full_fields(self):
        src = Source(title="文档.md", page=2, score=0.9, text="片段")
        assert src.page == 2


class TestQueryResponse:
    def test_all_fields_present(self):
        resp = QueryResponse(
            answer="答案",
            is_streaming=False,
            need_human=False,
            sources=[],
            session_id="s1",
            processing_time=0.1,
        )
        assert resp.sources == []
        assert resp.processing_time == 0.1

    def test_sources_validate_as_source_list(self):
        resp = QueryResponse(
            answer="答案",
            is_streaming=False,
            need_human=False,
            sources=[{"title": "t", "score": 0.9, "text": "x"}],
            session_id="s1",
            processing_time=0.1,
        )
        assert isinstance(resp.sources[0], Source)
