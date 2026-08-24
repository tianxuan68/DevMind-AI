# raw：T1 原始文档集

放置采集到的 Confluence/Wiki、Git 文档、Swagger/OpenAPI、runbook、复盘报告等原始文件。

## 按知识库分目录

| 目录 | 对应知识库 | 负责团队 |
|------|------------|----------|
| `raw/platform/` | 平台工程知识库 | 平台组 |
| `raw/security/` | 安全与合规知识库 | 安全组 |
| `raw/backend/` | 研发实践知识库 | 研发组 |

完整文档清单见 [docs/knowledge-bases/知识库文档索引.md](../../docs/knowledge-bases/知识库文档索引.md)。

## 元数据要求

每份 Markdown 顶部 YAML 块需包含：`title`、`team`、`system`、`doc_type`、`version`、`security_level`、`last_updated`。
