-- 更新预置知识库创建人为 admin（id=1）
-- 若知识库已存在且无 created_by，执行本脚本
USE internal_tech_kb;

UPDATE knowledge_bases SET created_by = 1 WHERE id IN (1, 2, 3) AND created_by IS NULL;
