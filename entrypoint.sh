#!/bin/sh
set -e

# T11: 等待 mysql / redis / milvus 可用后启动问答服务
# TODO(服务组): 增加依赖服务健康检查与重试逻辑。
exec uvicorn app:app --host 0.0.0.0 --port 8003
