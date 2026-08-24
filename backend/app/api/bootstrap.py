"""GET /api/client/bootstrap：客户端启动配置。"""
from fastapi import APIRouter

from backend.app.core.config import settings
from backend.app.services import oss_service

router = APIRouter()


@router.get("/api/client/bootstrap")
def bootstrap():
    return {
        "announcements": [],
        "help_links": [],
        "features": {
            "ossUpload": oss_service.is_enabled(),
            "ossRegion": settings.OSS_REGION if oss_service.is_enabled() else None,
            "ossBucket": settings.OSS_BUCKET if oss_service.is_enabled() else None,
        },
    }
