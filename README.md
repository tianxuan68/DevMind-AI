# DevMind-AI
企业内部技术知识库智能问答系统


## 项目目标

解决研发/运维/支持人员在多套内部系统（Wiki、代码库、接口文档、值班手册）中定位技术资料慢、重复提问、新人上手慢的问题。

## 技术栈

FastAPI + MySQL/BM25 + Redis + Milvus + BGE-M3 + bge-reranker-v2-m3 + DashScope LLM + React。

## 目录结构

完整目录与任务（T1–T14）映射见 [docs/项目目录结构.md](docs/项目目录结构.md)。

任务分工见 [docs/企业内部技术知识库智能问答系统-任务分工.md](docs/企业内部技术知识库智能问答系统-任务分工.md)。

## 参考基线项目

`E:\study_project\Itcast_qa_system`（黑马课程问答系统）。

## 启动

```shell
# 安装依赖
uv sync          # 或 pip install -r requirements.txt

# 启动依赖服务
cd docker/milvus_redis && docker compose up -d
cd docker/base_app && docker compose up -d

# 启动问答服务（端口 8003）
python app.py
```
