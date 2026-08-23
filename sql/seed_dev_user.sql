-- 开发环境测试账号（密码：123456）
-- 使用前请先执行 sql/schema.sql
-- 生成新密码哈希：python -c "from backend.app.core.security import hash_password; print(hash_password('123456'))"

USE internal_tech_kb;

INSERT INTO users (username, password_hash, nickname, phone, team, security_level)
VALUES (
    'admin',
    'pbkdf2_sha256$100000$5c487f646b5f285135817019ac20d2c6$d6158f4b4b9dd7b0e47b47c1b5b83111356d5785ca7ce7e288f0fc941f76b88f',
    '管理员',
    '13800000001',
    'platform',
    'team'
)
ON DUPLICATE KEY UPDATE
    password_hash = VALUES(password_hash),
    nickname = VALUES(nickname),
    phone = VALUES(phone),
    team = VALUES(team);
