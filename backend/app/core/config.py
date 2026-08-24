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

        # JWT / 安全（与 T8 SSO_SECRET 对齐：优先 JWT_SECRET，否则读 config.ini sso_secret）
        self.JWT_SECRET = os.getenv(
            "JWT_SECRET",
            parser.get("security", "sso_secret", fallback="devmind-ai-sso-secret"),
        )
        self.JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
        self.JWT_EXPIRE_HOURS = int(os.getenv("JWT_EXPIRE_HOURS", "168"))
        self.SMS_CODE_TTL = int(os.getenv("SMS_CODE_TTL", "300"))
        self.SMS_SEND_INTERVAL = int(os.getenv("SMS_SEND_INTERVAL", "60"))
        self.APP_DEBUG = os.getenv("APP_DEBUG", "false").lower() in {"1", "true", "yes", "on"}

        # 问题缓存：随机 TTL 防止缓存雪崩；空值短 TTL 防止穿透
        self.QUESTION_CACHE_TTL = int(os.getenv("QUESTION_CACHE_TTL", "600"))
        self.QUESTION_EMPTY_TTL = int(os.getenv("QUESTION_EMPTY_TTL", "60"))
        self.CACHE_LOCK_TIMEOUT = int(os.getenv("CACHE_LOCK_TIMEOUT", "5"))

        # 文档上传目录
        self.UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", str(PROJECT_ROOT / "data" / "uploads")))

        # 阿里云 OSS（Python SDK V2，凭证走 OSS_ACCESS_KEY_ID / OSS_ACCESS_KEY_SECRET）
        self.OSS_ENABLED = os.getenv("OSS_ENABLED", parser.get("oss", "enabled", fallback="false")).lower() in {
            "1", "true", "yes", "on",
        }
        self.OSS_REGION = os.getenv("OSS_REGION", parser.get("oss", "region", fallback=""))
        self.OSS_BUCKET = os.getenv("OSS_BUCKET", parser.get("oss", "bucket", fallback=""))
        self.OSS_ENDPOINT = os.getenv("OSS_ENDPOINT", parser.get("oss", "endpoint", fallback=""))
        self.OSS_PREFIX = os.getenv("OSS_PREFIX", parser.get("oss", "prefix", fallback="devmind-ai"))
        self.OSS_PRESIGN_EXPIRES = int(os.getenv("OSS_PRESIGN_EXPIRES", parser.get("oss", "presign_expires_seconds", fallback="3600")))

        # 日志
        self.LOG_DIR = Path(os.getenv("LOG_DIR", str(PROJECT_ROOT / "logs")))
        self.LOG_FILE_NAME = os.getenv("LOG_FILE_NAME", "backend.log")

        # Spug 短信（凭证请通过环境变量注入）
        self.SPUG_SMS_ENABLED = os.getenv("SPUG_SMS_ENABLED", parser.get("sms", "enabled", fallback="false")).lower() in {
            "1", "true", "yes", "on",
        }
        self.SPUG_SMS_MODE = os.getenv("SPUG_SMS_MODE", parser.get("sms", "mode", fallback="send"))
        self.SPUG_SMS_TEMPLATE = os.getenv("SPUG_SMS_TEMPLATE", parser.get("sms", "template", fallback="k2RVBmyzanj0ny3b"))
        default_sms_api = f"https://push.spug.cc/sms/{self.SPUG_SMS_TEMPLATE}"
        self.SPUG_SMS_API_URL = os.getenv("SPUG_SMS_API_URL", parser.get("sms", "api_url", fallback=default_sms_api))
        self.SPUG_SMS_SEND_URL = os.getenv(
            "SPUG_SMS_SEND_URL",
            parser.get("sms", "send_url", fallback=f"https://push.spug.cc/send/{self.SPUG_SMS_TEMPLATE}"),
        )
        self.SPUG_SMS_APP_NAME = os.getenv("SPUG_SMS_APP_NAME", parser.get("sms", "app_name", fallback="DevMind AI"))
        self.SPUG_SMS_APP_KEY = os.getenv("SPUG_SMS_APP_KEY", parser.get("sms", "app_key", fallback=""))
        self.SPUG_SMS_CREDENTIAL = os.getenv("SPUG_SMS_CREDENTIAL", parser.get("sms", "credential", fallback=""))
        self.SPUG_SMS_NUMBER = os.getenv("SPUG_SMS_NUMBER", parser.get("sms", "number", fallback="10"))
        self.SPUG_SMS_TIMEOUT = int(os.getenv("SPUG_SMS_TIMEOUT", parser.get("sms", "timeout", fallback="10")))


settings = Settings()
