"""T12 客户端后端 API。"""
from fastapi import APIRouter

from .bootstrap import router as bootstrap_router

api_router = APIRouter()
api_router.include_router(bootstrap_router)
