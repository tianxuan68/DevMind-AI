"""DevMind-AI 问答服务入口（T8）。

接口契约以 docs/api/接口文档.md 为准（契约先行定稿）：
- GET  /health
- POST /api/create_session
- POST /api/query
- WS   /api/stream
- GET  /api/sources
- POST /api/feedback

启动：python app.py（端口 8003，见 config.ini [app].port）
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from base.config import Config
from internal_kb_qa.api.routers import api_router
from new_main import IntegratedQASystem

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    config = Config()
    qa_system = IntegratedQASystem(config)
    app.state.qa_system = qa_system
    logger.info(
        "问答系统初始化完成（sso_mode=%s, ticket_enabled=%s）",
        config.SSO_MODE,
        config.TICKET_ENABLED,
    )
    yield
    if qa_system.ticket_service.db is not None:
        qa_system.ticket_service.db.close()
        logger.info("工单服务 MySQL 连接已关闭")


app = FastAPI(title="DevMind-AI 企业内部技术知识库智能问答系统", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host="0.0.0.0", port=Config().APP_PORT, reload=False)
