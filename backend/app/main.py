"""DevMind-AI 后端服务入口。

统一挂载工作台 API（auth/knowledge/faq）与 T8 问答 API（query/stream/feedback）。

启动方式：
    uv run uvicorn backend.app.main:app --host 0.0.0.0 --port 8004
"""
import os

# 在任何 ML 库导入前限制线程，降低 Windows 下模型加载内存峰值
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
# 工作台 JWT 与 T8 SSO 共用密钥时，默认走 jwt 模式（可被 SSO_MODE 覆盖）
if os.getenv("JWT_SECRET"):
    os.environ.setdefault("SSO_MODE", "jwt")

from contextlib import asynccontextmanager

import asyncio

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.api import api_router
from backend.app.core.db import db
from backend.app.core.logging_config import setup_logging
from base.logger import logger
from internal_kb_qa.api.routers import api_router as qa_api_router

setup_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.connect()

    from base.config import Config
    from new_main import IntegratedQASystem

    config = Config()
    qa_system = IntegratedQASystem(config)
    app.state.qa_system = qa_system
    logger.info(
        "问答系统已挂载到后端（sso_mode=%s, ticket_enabled=%s）",
        config.SSO_MODE,
        config.TICKET_ENABLED,
    )

    if os.getenv("RETRIEVAL_WARMUP", "false").lower() in {"1", "true", "yes", "on"}:
        asyncio.create_task(_warmup_retrieval())

    yield

    if getattr(qa_system.ticket_service, "db", None) is not None:
        try:
            qa_system.ticket_service.db.close()
        except Exception as exc:
            logger.warning("关闭工单 MySQL 连接失败: %s", exc)
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
app.include_router(qa_api_router)


@app.get("/health")
async def health():
    return {"status": "healthy"}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8004)
