---
title: Python 与 FastAPI 开发规范
category: tech
team: backend
system: devmind_ai
doc_type: wiki
version: 1.0
security_level: public
last_updated: 2026-08-23
knowledge_base: 研发实践知识库
---

# Python 与 FastAPI 开发规范

## 项目结构

```
backend/app/
  api/          # 路由
  core/         # 配置、数据库、安全
  services/     # 业务逻辑
internal_kb_qa/ # RAG 管道
```

## 约定

- 异步路由 + `aiomysql` 连接池
- 阻塞操作（向量检索、模型推理）使用 `asyncio.to_thread`
- 配置从 `config.ini` + 环境变量读取
- 日志使用 `base.logger`

## API 设计

- 统一前缀 `/api`
- 需登录接口依赖 `get_current_user`
- 错误使用 `HTTPException`，返回 `detail` 字符串

## Java 命名规范（交叉引用）

企业 Java 项目遵循《Java 开发手册》，包名全小写、类名大驼峰、常量全大写下划线。Python 模块使用 snake_case。
