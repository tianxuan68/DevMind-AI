-- =============================================================================
-- DevMind-AI 企业内部技术知识库智能问答系统 · 数据库建库脚本
--
-- 依据：docs/企业内部技术知识库智能问答系统-任务分工.md
--   T5  高频技术 FAQ 精确匹配（MySQL + BM25）
--   T8  问答服务 API（会话历史 / 用户反馈 / 转人工工单）
--   T1  文档元数据登记（版本管理与失效标记）
--   T11 权限隔离验证（用户-团队-权限映射，用于测试账号）
--
-- 参考基线：E:/study_project/Itcast_qa_system（jpkb / conversations 表）
--
-- 使用方式：
--   mysql -u root -p < schema.sql
--   或在 MySQL 客户端中执行：SOURCE E:/tianxuan/DevMind-AI/sql/schema.sql;
--
-- 说明：数据库名 internal_tech_kb 与 config.ini 中 [mysql] database 保持一致；
--       本脚本不包含任何真实数据与账号口令，密码请通过环境变量/配置注入。
-- =============================================================================

CREATE DATABASE IF NOT EXISTS internal_tech_kb
    DEFAULT CHARACTER SET utf8mb4
    DEFAULT COLLATE utf8mb4_general_ci;

USE internal_tech_kb;

SET NAMES utf8mb4;

-- -----------------------------------------------------------------------------
-- T5: 高频技术 FAQ 表（BM25 精确/模糊匹配，命中即秒回，不进 LLM）
-- 字段对齐 internal_kb_qa/data/faq/README.md 中的 FAQ 表结构
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS faq (
    id              BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
    question        VARCHAR(1000)   NOT NULL COMMENT '标准问题（用户高频问法）',
    keywords        VARCHAR(2000)   DEFAULT NULL COMMENT '关键词/同义词，空格分隔，便于 BM25',
    answer          TEXT            NOT NULL COMMENT '标准答案',
    doc_source      VARCHAR(1000)   DEFAULT NULL COMMENT '答案出处（文档名/链接）',
    category        VARCHAR(100)    DEFAULT NULL COMMENT '类别：环境配置/权限申请/常见报错/流程规范等',
    team            VARCHAR(100)    DEFAULT NULL COMMENT '所属团队：infra/backend/frontend/data/ops',
    system_name     VARCHAR(100)    DEFAULT NULL COMMENT '所属系统/服务名（避开 MySQL 保留字 SYSTEM）',
    security_level  VARCHAR(20)     NOT NULL DEFAULT 'team' COMMENT '权限等级：public/team/confidential',
    version         VARCHAR(50)     DEFAULT NULL COMMENT '版本号',
    is_active       TINYINT(1)      NOT NULL DEFAULT 1 COMMENT '是否有效（过期文档置 0，不再参与匹配）',

    last_updated    DATETIME        DEFAULT NULL COMMENT '内容最后更新时间（对应文档更新时间）',
    created_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uniq_faq_question (question(255)) COMMENT '标准问题去重，禁止重复写入',
    KEY idx_faq_team (team),
    KEY idx_faq_category (category),
    KEY idx_faq_active (is_active)
    ) ENGINE = InnoDB
  DEFAULT CHARSET = utf8mb4
  COMMENT = 'T5 高频技术 FAQ：标准问题、标准答案、文档出处、类别、团队';

-- -----------------------------------------------------------------------------
-- T1/T2: 文档元数据登记表（知识库文档清单，版本管理与失效标记）
-- 注意：文档向量与 chunk 内容存 Milvus，本表只存元数据
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS documents (
    id              BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
    doc_source      VARCHAR(1000)   NOT NULL COMMENT '来源文件/页面（Confluence URL、Git 路径等，避开 MySQL 保留字 SOURCE）',
    doc_type        VARCHAR(50)     NOT NULL COMMENT '文档类型：wiki/api/runbook/faq/report',
    team            VARCHAR(100)    DEFAULT NULL COMMENT '所属团队',
    system_name     VARCHAR(100)    DEFAULT NULL COMMENT '所属系统/服务名（避开 MySQL 保留字 SYSTEM）',
    version         VARCHAR(50)     DEFAULT NULL COMMENT '文档版本',
    security_level  VARCHAR(20)     NOT NULL DEFAULT 'team' COMMENT '权限等级：public/team/confidential',
    status          VARCHAR(20)     NOT NULL DEFAULT 'active' COMMENT 'active 生效 / deprecated 已失效',
    chunk_count     INT UNSIGNED    DEFAULT 0 COMMENT '切分入库的 chunk 数量',
    last_updated    DATETIME        DEFAULT NULL COMMENT '文档源最后更新时间',
    created_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uniq_document (doc_source(255), doc_type) COMMENT '同一来源同一类型文档唯一',
    KEY idx_documents_team (team, security_level),
    KEY idx_documents_status (status)
) ENGINE = InnoDB
  DEFAULT CHARSET = utf8mb4
  COMMENT = 'T1 文档元数据：team/system/security_level/version/失效标记';

-- -----------------------------------------------------------------------------
-- T8: 会话历史表（参考基线 new_main.py 中的 conversations 表，扩展 user/team）
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS conversations (
    id          BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
    session_id  VARCHAR(36)     NOT NULL COMMENT '会话 ID（/api/create_session 生成的 UUID）',
    user        VARCHAR(64)     DEFAULT NULL COMMENT '提问用户（SSO 账号）',
    team        VARCHAR(100)    DEFAULT NULL COMMENT '用户团队',
    question    TEXT            NOT NULL COMMENT '用户问题',
    answer      MEDIUMTEXT      NOT NULL COMMENT '回答内容',
    timestamp   DATETIME        NOT NULL COMMENT '时间',
    PRIMARY KEY (id),
    KEY idx_conversations_session (session_id) COMMENT '按会话查询最近 N 轮历史',
    KEY idx_conversations_user (user),
    KEY idx_conversations_time (timestamp)
) ENGINE = InnoDB
  DEFAULT CHARSET = utf8mb4
  COMMENT = 'T8 会话历史：保留最近 N 轮对话供指代补全';

-- -----------------------------------------------------------------------------
-- T8: 用户反馈表（/api/feedback，点赞点踩、转人工、反馈回写知识库）
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS feedback (
    id          BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
    session_id  VARCHAR(36)     NOT NULL COMMENT '会话 ID',
    user        VARCHAR(64)     DEFAULT NULL COMMENT '反馈用户',
    team        VARCHAR(100)    DEFAULT NULL COMMENT '用户团队',
    user_query  TEXT            NOT NULL COMMENT '对应的问题（避开 MySQL 保留字 QUERY）',
    rating      TINYINT         DEFAULT NULL COMMENT '1-5 评分',
    comment     TEXT            DEFAULT NULL COMMENT '文字反馈',
    need_human  TINYINT(1)      NOT NULL DEFAULT 0 COMMENT '是否要求人工处理',
    ticket_id   VARCHAR(64)     DEFAULT NULL COMMENT '关联工单号（need_human=1 时回填）',
    status      VARCHAR(20)     NOT NULL DEFAULT 'new' COMMENT '反馈处理状态：new/reviewed/merged（已回写知识库）',
    created_at  DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_feedback_session (session_id),
    KEY idx_feedback_user (user),
    KEY idx_feedback_status (status),
    KEY idx_feedback_created (created_at)
) ENGINE = InnoDB
  DEFAULT CHARSET = utf8mb4
  COMMENT = 'T8 用户反馈：差评/转人工问题每周复核后回写 FAQ 与知识库';

-- -----------------------------------------------------------------------------
-- T8: 转人工工单表（低置信度/投诉/故障上报 100% 转人工兜底）
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tickets (
    id          BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
    ticket_no   VARCHAR(64)     NOT NULL COMMENT '工单号（对接外部工单系统时同步）',
    session_id  VARCHAR(36)     NOT NULL COMMENT '会话 ID',
    user        VARCHAR(64)     DEFAULT NULL COMMENT '提问用户',
    team        VARCHAR(100)    DEFAULT NULL COMMENT '用户团队',
    user_query  TEXT            NOT NULL COMMENT '问题内容（避开 MySQL 保留字 QUERY）',
    reason      VARCHAR(50)     NOT NULL COMMENT '转人工原因：low_confidence/complaint/incident/user_request',
    priority    VARCHAR(20)     NOT NULL DEFAULT 'normal' COMMENT '优先级：low/normal/high/urgent',
    status      VARCHAR(20)     NOT NULL DEFAULT 'pending' COMMENT 'pending/processing/done/closed',
    assignee    VARCHAR(64)     DEFAULT NULL COMMENT '处理人',
    created_at  DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    resolved_at DATETIME        DEFAULT NULL COMMENT '解决时间',
    PRIMARY KEY (id),
    UNIQUE KEY uniq_ticket_no (ticket_no),
    KEY idx_tickets_session (session_id),
    KEY idx_tickets_status (status),
    KEY idx_tickets_team (team),
    KEY idx_tickets_created (created_at)
) ENGINE = InnoDB
  DEFAULT CHARSET = utf8mb4
  COMMENT = 'T8 转人工工单：低置信度/投诉/故障上报兜底队列';

-- -----------------------------------------------------------------------------
-- T8/T11: 用户与团队权限映射表（SSO 本地缓存 / 权限隔离验证测试账号）
-- 注意：生产环境以 SSO 为准，本表用于本地映射与验收测试（越权检索命中数=0）
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    id              BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
    username        VARCHAR(64)     NOT NULL COMMENT '登录账号',
    password_hash   VARCHAR(255)    NOT NULL COMMENT '密码哈希（PBKDF2-SHA256）',
    nickname        VARCHAR(100)    DEFAULT NULL COMMENT '昵称/姓名',
    phone           VARCHAR(20)     DEFAULT NULL COMMENT '手机号（登录/验证码）',
    team            VARCHAR(100)    DEFAULT 'default' COMMENT '所属团队：infra/backend/frontend/data/ops',
    security_level  VARCHAR(20)     NOT NULL DEFAULT 'team' COMMENT '最高可见权限：public/team/confidential',
    is_active       TINYINT(1)      NOT NULL DEFAULT 1,
    created_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uniq_username (username),
    UNIQUE KEY uniq_phone (phone),
    KEY idx_users_team (team)
) ENGINE = InnoDB
  DEFAULT CHARSET = utf8mb4
  COMMENT = 'T8 用户-团队-权限映射：本地注册登录 + 权限隔离验证';

-- =============================================================================
-- 建库完成。后续数据写入脚本：
--   FAQ 导入:   internal_kb_qa/scripts/build_faq.py -> mysql_qa/db/mysql_client.py
--   文档入库:   internal_kb_qa/scripts/ingest_documents.py（documents 表 + Milvus）
-- =============================================================================
