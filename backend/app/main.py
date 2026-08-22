"""T12 客户端后端服务入口。"""
from fastapi import FastAPI

from app.api import api_router

app = FastAPI(title="DevMind-AI Client Backend")
app.include_router(api_router)

# TODO(T12 后端组): 挂载 SSO 鉴权、公告/帮助内容、用户偏好等接口。
