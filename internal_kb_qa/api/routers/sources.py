"""GET /api/sources：可选系统/团队过滤项（读配置，与权限无关的静态列表）。"""
from fastapi import APIRouter, Depends, Request

from internal_kb_qa.api.deps import UserContext, get_current_user

router = APIRouter()


@router.get("/api/sources")
def sources(request: Request, user: UserContext = Depends(get_current_user)):
    return {"sources": request.app.state.qa_system.config.VALID_SOURCES}
