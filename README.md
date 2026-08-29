# DevMind-AI
企业内部技术知识库智能问答系统


## 项目目标

解决研发/运维/支持人员在多套内部系统（Wiki、代码库、接口文档、值班手册）中定位技术资料慢、重复提问、新人上手慢的问题。

## 技术栈

FastAPI + PostgreSQL 16/BM25 + Redis + Milvus + BGE-M3 + bge-reranker-v2-m3 + DashScope LLM + React。

## 目录结构

完整目录与任务（T1–T14）映射见 [docs/项目目录结构.md](docs/项目目录结构.md)。

任务分工见 [docs/企业内部技术知识库智能问答系统-任务分工.md](docs/企业内部技术知识库智能问答系统-任务分工.md)。

## 启动

```powershell
# 安装依赖
uv sync

# 启动认证、文档存储和向量索引依赖
docker compose -f docker/docker-compose.yml up -d postgres redis minio etcd milvus clamav

# 首次启用文档向量索引时准备模型
uv run python -m internal_kb_qa.scripts.download_models bge-m3

# 启动正式后端（端口 15200）
uv run python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 15200 --reload

# 另开一个终端启动文档任务 Worker
uv run python -m backend.app.worker
```

本地配置按需将 `config.local.ini.example` 复制为 `config.local.ini`；环境变量仍具有最高优先级。启动后访问：

- 存活检查：`http://127.0.0.1:15200/health`
- 依赖就绪检查：`http://127.0.0.1:15200/health/ready`
- OpenAPI：`http://127.0.0.1:15200/docs`

正式接口统一使用 `/api/v1`。后端分层与实施方案见 [后端架构设计](docs/architecture/后端架构设计.md)。

数据备份、完整性校验和隔离恢复演练见 [备份与恢复](docs/deployment/备份与恢复.md)。

生产初始化、升级、回滚和发布验收见 [管理员手册与发布验收](docs/deployment/管理员手册与发布验收.md)。

### 启动前端

保持后端运行，另开一个 PowerShell：

```powershell
cd D:\DevMind-AI\front
npm install
npm run dev
```

访问 `http://127.0.0.1:5173/`。页面路径分别为：展示页 `/`、登录页 `/login`、功能工作台 `/workspace`。Vite 会把 HTTP 和 WebSocket `/api` 请求代理至 `127.0.0.1:15200`。
