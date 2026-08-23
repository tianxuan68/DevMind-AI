"""POST /api/create_session：创建会话（UUID + Redis 会话初始化）。"""
import uuid

from fastapi import APIRouter, Depends, Request

from internal_kb_qa.api.deps import UserContext, get_current_user

router = APIRouter()


@router.post("/api/create_session")
def create_session(request: Request, user: UserContext = Depends(get_current_user)):
    session_id = str(uuid.uuid4())
    request.app.state.qa_system.redis.set_session(session_id, [])
    return {"session_id": session_id}
