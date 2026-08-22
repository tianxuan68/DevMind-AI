-- 企业内部技术知识库 FAQ 表（T1/T5）
-- 字段与 internal_kb_qa/data/faq/README.md 对齐，并兼容现有 MySQL 库实际结构
CREATE TABLE IF NOT EXISTS `faq` (
    `id` bigint unsigned NOT NULL AUTO_INCREMENT COMMENT '主键',
    `question` varchar(1000) NOT NULL COMMENT '标准问题（用户高频问法）',
    `keywords` varchar(2000) DEFAULT NULL COMMENT '关键词/同义词，空格分隔，便于 BM25',
    `answer` text NOT NULL COMMENT '标准答案',
    `doc_source` varchar(1000) DEFAULT NULL COMMENT '答案出处（文档名/链接）',
    `category` varchar(100) DEFAULT NULL COMMENT '类别：环境配置/权限申请/常见报错/流程规范等',
    `team` varchar(100) DEFAULT NULL COMMENT '所属团队：infra/backend/frontend/data/ops',
    `system_name` varchar(100) DEFAULT NULL COMMENT '所属系统/服务名（避开 MySQL 保留字 SYSTEM）',
    `security_level` varchar(20) NOT NULL DEFAULT 'team' COMMENT '权限等级：public/team/confidential',
    `version` varchar(50) DEFAULT NULL COMMENT '版本号',
    `is_active` tinyint(1) NOT NULL DEFAULT '1' COMMENT '是否有效（过期文档置 0，不再参与匹配）',
    `last_updated` datetime DEFAULT NULL COMMENT '内容最后更新时间（对应文档更新时间）',
    `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    UNIQUE KEY `uniq_faq_question` (`question`(255)) COMMENT '标准问题去重，禁止重复写入',
    KEY `idx_faq_team` (`team`),
    KEY `idx_faq_category` (`category`),
    KEY `idx_faq_active` (`is_active`),
    FULLTEXT KEY `ft_faq_question` (`question`, `keywords`) /*!50100 WITH PARSER `ngram` */
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='T5 高频技术 FAQ：标准问题、标准答案、文档出处、类别、团队';
