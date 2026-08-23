"""POST /api/feedback：点赞点踩、评论、转人工。

need_human=true 时创建工单（落库 + Redis 队列 + 外部工单系统同步），
返回 ticket_id；反馈落库供知识库闭环回写（T1 数据组消费）。
"""
from fastapi import APIRouter, Depends, Request

from internal_kb_qa.api.deps import UserContext, get_current_user
from internal_kb_qa.api.schemas.request import FeedbackRequest
from internal_kb_qa.api.schemas.response import FeedbackResponse

router = APIRouter()


@router.post("/api/feedback", response_model=FeedbackResponse)
def feedback(
    payload: FeedbackRequest,
    request: Request,
    user: UserContext = Depends(get_current_user),
):
    result = request.app.state.qa_system.ticket_service.handle_feedback(
        session_id=payload.session_id,
        query=payload.query,
        user_id=user.user_id,
        team=user.team,
        rating=payload.rating,
        comment=payload.comment,
        need_human=bool(payload.need_human),
    )
    return FeedbackResponse(**result)
