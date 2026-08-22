"""DevMind-AI 后端服务入口。

启动方式：
    cd backend
    uvicorn app.main:app --host 0.0.0.0 --port 8004 --reload
"""
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.api import api_router
from backend.app.core.db import db


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时创建 MySQL/Redis 连接池
    await db.connect()
    yield
    # 关闭时释放连接池
    await db.close()


app = FastAPI(title="DevMind-AI Backend", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.get("/health")
async def health():
    return {"status": "healthy"}

if __name__ == '__main__':
    uvicorn.run(app, host="0.0.0.0", port=8004)
