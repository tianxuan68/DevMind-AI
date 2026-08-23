"""后端服务配置。

配置优先级：环境变量 > config.ini（项目根目录）
"""
import configparser
import os
from pathlib import Path

# backend/app/core/config.py -> 项目根目录
PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings:
    def __init__(self):
        parser = configparser.ConfigParser()
        parser.read(PROJECT_ROOT / "config.ini", encoding="utf-8")

        # MySQL
        self.MYSQL_HOST = os.getenv("MYSQL_HOST", parser.get("mysql", "host", fallback="localhost"))
        self.MYSQL_PORT = int(os.getenv("MYSQL_PORT", parser.get("mysql", "port", fallback="3306")))
        self.MYSQL_USER = os.getenv("MYSQL_USER", parser.get("mysql", "user", fallback="root"))
        self.MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", parser.get("mysql", "password", fallback=""))
        self.MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", parser.get("mysql", "database", fallback="internal_tech_kb"))
        self.MYSQL_POOL_SIZE = int(os.getenv("MYSQL_POOL_SIZE", "20"))
        self.MYSQL_POOL_MINSIZE = int(os.getenv("MYSQL_POOL_MINSIZE", "2"))

        # Redis 公共连接参数
        self.REDIS_HOST = os.getenv("REDIS_HOST", parser.get("redis", "host", fallback="localhost"))
        self.REDIS_PORT = int(os.getenv("REDIS_PORT", parser.get("redis", "port", fallback="6379")))
        self.REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", parser.get("redis", "password", fallback=""))
        self.REDIS_DB = int(os.getenv("REDIS_DB", parser.get("redis", "db", fallback="0")))

        # Redis 业务库隔离：
        # 1 = 短信验证码；2 = 用户问题缓存；3 = JWT 黑名单
        self.REDIS_SMS_DB = int(os.getenv("REDIS_SMS_DB", "1"))
        self.REDIS_QUESTION_DB = int(os.getenv("REDIS_QUESTION_DB", "2"))
        self.REDIS_TOKEN_DB = int(os.getenv("REDIS_TOKEN_DB", "3"))

        # JWT / 安全
        self.JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret-change-me")
        self.JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
        self.JWT_EXPIRE_HOURS = int(os.getenv("JWT_EXPIRE_HOURS", "168"))
        self.SMS_CODE_TTL = int(os.getenv("SMS_CODE_TTL", "300"))
        self.SMS_SEND_INTERVAL = int(os.getenv("SMS_SEND_INTERVAL", "60"))
        self.APP_DEBUG = os.getenv("APP_DEBUG", "true").lower() in {"1", "true", "yes", "on"}

        # 问题缓存：随机 TTL 防止缓存雪崩；空值短 TTL 防止穿透
        self.QUESTION_CACHE_TTL = int(os.getenv("QUESTION_CACHE_TTL", "600"))
        self.QUESTION_EMPTY_TTL = int(os.getenv("QUESTION_EMPTY_TTL", "60"))
        self.CACHE_LOCK_TIMEOUT = int(os.getenv("CACHE_LOCK_TIMEOUT", "5"))

        # 文档上传目录
        self.UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", str(PROJECT_ROOT / "data" / "uploads")))


settings = Settings()
