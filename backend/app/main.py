"""DevMind-AI 后端服务入口。

启动方式：
    cd backend
    uvicorn app.main:app --host 0.0.0.0 --port 8004 --reload
"""
import os

# 在任何 ML 库导入前限制线程，降低 Windows 下模型加载内存峰值
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")

from contextlib import asynccontextmanager

import asyncio

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.api import api_router
from backend.app.core.db import db
from backend.app.core.logging_config import setup_logging
from base.logger import logger

setup_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时创建 MySQL/Redis 连接池
    await db.connect()
    # 默认关闭预热，避免 Windows 低内存环境下启动即加载 BGE-M3 导致进程崩溃
    if os.getenv("RETRIEVAL_WARMUP", "false").lower() in {"1", "true", "yes", "on"}:
        asyncio.create_task(_warmup_retrieval())
    yield
    # 关闭时释放连接池
    await db.close()


async def _warmup_retrieval() -> None:
    try:
        from internal_kb_qa.core.hybrid_search import warmup

        await asyncio.to_thread(warmup)
        logger.info("检索模型预热完成")
    except Exception as exc:
        logger.warning("检索模型预热跳过: %s", exc)


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
