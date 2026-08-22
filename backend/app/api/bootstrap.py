"""GET /api/client/bootstrap：客户端启动配置。"""
from fastapi import APIRouter

router = APIRouter()


@router.get("/api/client/bootstrap")
def bootstrap():
    # TODO(T12 后端组): announcements / help_links / features。
    return {"announcements": [], "help_links": [], "features": {}}
