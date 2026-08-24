-- 知识库与文档扩展迁移（在 internal_tech_kb 库执行）
USE internal_tech_kb;

CREATE TABLE IF NOT EXISTS knowledge_bases (
    id              BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
    name            VARCHAR(200)    NOT NULL COMMENT '知识库名称',
    description     VARCHAR(500)    DEFAULT NULL COMMENT '描述',
    owner_team      VARCHAR(100)    DEFAULT NULL COMMENT '负责团队',
    status          VARCHAR(20)     NOT NULL DEFAULT 'active' COMMENT 'active/archived',
    created_by      BIGINT UNSIGNED DEFAULT NULL COMMENT '创建人 users.id',
    created_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uniq_kb_name (name),
    KEY idx_kb_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='知识库';

-- 以下 ALTER 若列已存在会报错，可忽略 Duplicate column 后继续
ALTER TABLE documents ADD COLUMN knowledge_base_id BIGINT UNSIGNED DEFAULT NULL COMMENT '所属知识库' AFTER id;
ALTER TABLE documents ADD COLUMN file_name VARCHAR(500) DEFAULT NULL COMMENT '展示文件名' AFTER knowledge_base_id;
ALTER TABLE documents ADD COLUMN size_bytes BIGINT UNSIGNED DEFAULT NULL COMMENT '文件大小字节' AFTER file_name;
ALTER TABLE documents ADD COLUMN mime_type VARCHAR(100) DEFAULT NULL COMMENT 'MIME 类型' AFTER size_bytes;
ALTER TABLE documents ADD COLUMN storage_path VARCHAR(1000) DEFAULT NULL COMMENT '本地存储路径' AFTER mime_type;
ALTER TABLE documents ADD COLUMN created_by BIGINT UNSIGNED DEFAULT NULL COMMENT '上传人 users.id' AFTER storage_path;
ALTER TABLE documents ADD COLUMN index_status VARCHAR(20) DEFAULT 'indexed' COMMENT 'processing/indexed/failed' AFTER created_by;
ALTER TABLE documents ADD KEY idx_documents_kb (knowledge_base_id, index_status);

INSERT IGNORE INTO knowledge_bases (id, name, description, owner_team, status, created_by) VALUES
(1, '平台工程知识库', '平台架构、中间件与工程规范', '平台组', 'active', 1),
(2, '安全与合规知识库', '安全基线、合规与身份认证', '安全组', 'active', 1),
(3, '研发实践知识库', '研发流程、CI/CD 与代码规范', '研发组', 'active', 1);
