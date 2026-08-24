"""POST /api/query（非流式：闲聊 / FAQ 命中 / 兜底转人工）。

需要 RAG 主链路时返回 is_streaming=true，前端切换 WS /api/stream。
"""
import time

from fastapi import APIRouter, Depends, Request

from internal_kb_qa.api.deps import UserContext, get_current_user
from internal_kb_qa.api.schemas.request import QueryRequest
from internal_kb_qa.api.schemas.response import QueryResponse

router = APIRouter()


@router.post("/api/query", response_model=QueryResponse)
def query(
    payload: QueryRequest,
    request: Request,
    user: UserContext = Depends(get_current_user),
):
    start_time = time.time()
    result = request.app.state.qa_system.query_sync(
        payload.query, payload.session_id, payload.source_filter, user
    )
    return QueryResponse(
        answer=result.answer,
        is_streaming=result.is_streaming,
        need_human=result.need_human,
        sources=result.sources,
        session_id=result.session_id,
        processing_time=round(time.time() - start_time, 3),
    )
