-- FAQ 种子数据：与三库文档内容对齐，供 T5 MySQL 精确匹配
-- 使用前请先执行 sql/schema.sql
-- 执行：mysql -uroot -p internal_tech_kb < sql/seed_faq.sql

USE internal_tech_kb;

INSERT INTO faq (question, keywords, answer, doc_source, category, team, system_name, security_level, version, last_updated, is_active) VALUES
(
  'Python 项目环境初始化怎么做？',
  'Python uv sync venv 环境安装 依赖',
  '推荐使用 uv：在项目根目录执行 uv sync。不使用 uv 时，创建 venv 后 pip install -r requirements.txt。依赖安装慢可配置公司内网 PyPI 镜像。',
  'Python与FastAPI开发规范.md',
  '环境配置',
  'backend',
  'devmind_ai',
  'public',
  '1.0',
  '2026-08-23 00:00:00',
  1
),
(
  'MySQL 连接池默认配置是什么？',
  'MySQL 连接池 pool size 默认配置',
  'DevMind-AI 后端默认 MySQL 连接池大小为 20（MYSQL_POOL_SIZE），最小连接数 2。连接失败时请确认 host、port、密码与 Docker MySQL 一致。',
  'Python与FastAPI开发规范.md',
  '环境配置',
  'infra',
  'devmind_ai',
  'team',
  '1.0',
  '2026-08-23 00:00:00',
  1
),
(
  '生产环境如何配置统一身份认证？',
  'OIDC SSO 统一身份认证 RBAC MFA',
  '推荐采用 OIDC + 企业 SSO：接入企业 IdP 并启用 MFA，通过 RBAC 映射部门与知识库权限，记录登录与文档访问审计日志。DevMind-AI 当前支持账号密码与手机验证码登录，生产需配置 JWT_SECRET 并关闭 APP_DEBUG。',
  '统一身份认证接入规范.md',
  '权限申请',
  'infra',
  'devmind_ai',
  'team',
  '1.0',
  '2026-08-23 00:00:00',
  1
),
(
  'Milvus 为什么适合企业级 RAG？',
  'Milvus RAG 向量 企业级 分布式 检索',
  'Milvus 适合企业级 RAG 的原因：1）云原生分布式架构，支持弹性扩展；2）亿级向量规模下毫秒级检索；3）支持稠密+稀疏混合检索，兼顾术语与语义；4）存储计算解耦，便于长期演进。',
  'Milvus向量库使用指南.md',
  '架构设计',
  'infra',
  'devmind_ai',
  'team',
  '1.0',
  '2026-08-23 00:00:00',
  1
),
(
  'P0 故障响应要求是什么？',
  'P0 故障 响应 应急 分级',
  'P0 级故障包括：核心业务完全不可用、大规模数据丢失或错误、严重安全泄露。响应要求：立即拉群，5 分钟内响应，相关负责人必须介入。',
  '故障上报与应急响应规范.md',
  '故障上报',
  'ops',
  'devmind_ai',
  'team',
  '1.0',
  '2026-08-22 00:00:00',
  1
),
(
  '如何提交权限申请？',
  '权限申请 工单 审批 开通',
  '登录内部工单系统 → 选择「权限申请」→ 填写目标系统、权限类型、原因与期限 → 等待负责人审批 → 管理员开通。DevMind-AI 知识库权限联系平台工程组。',
  '权限申请与审批流程.md',
  '权限申请',
  'infra',
  'devmind_ai',
  'public',
  '1.0',
  '2026-08-23 00:00:00',
  1
),
(
  'DevMind-AI 如何启动？',
  'DevMind 启动 docker compose uvicorn npm',
  '1）cd docker && docker compose up -d 启动 MySQL/Redis/Milvus；2）uv sync 安装依赖；3）uv run uvicorn backend.app.main:app --port 8004 启动后端；4）cd front && npm run dev 启动前端。',
  'DevMind-AI部署运维手册.md',
  '环境配置',
  'infra',
  'devmind_ai',
  'team',
  '1.0',
  '2026-08-23 00:00:00',
  1
),
(
  '文档入库向量库的命令是什么？',
  'ingest_documents 向量 入库 Milvus',
  '执行：uv run python -m internal_kb_qa.scripts.ingest_documents --dir internal_kb_qa/data/raw。重建索引加 --recreate。需先 download_models 并确保 Milvus 已启动。',
  'RAG检索链路说明.md',
  '环境配置',
  'infra',
  'devmind_ai',
  'team',
  '1.0',
  '2026-08-23 00:00:00',
  1
)
ON DUPLICATE KEY UPDATE
  answer = VALUES(answer),
  keywords = VALUES(keywords),
  doc_source = VALUES(doc_source),
  last_updated = VALUES(last_updated);
