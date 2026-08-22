"""后端 API 路由聚合。"""
from fastapi import APIRouter

from .auth import router as auth_router
from .bootstrap import router as bootstrap_router
from .faq import router as faq_router
from .knowledge import router as knowledge_router
from .user import router as user_router

api_router = APIRouter()
api_router.include_router(bootstrap_router)
api_router.include_router(auth_router)
api_router.include_router(user_router)
api_router.include_router(knowledge_router)
api_router.include_router(faq_router)
