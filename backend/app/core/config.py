"""T12 客户端后端配置。"""
import os


class Settings:
    MYSQL_HOST = os.getenv("MYSQL_HOST", "localhost")
    MYSQL_USER = os.getenv("MYSQL_USER", "root")
    MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
    MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "internal_tech_kb")
    REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT = int(os.getenv("REDIS_PORT", "16379"))
    CLIENT_BACKEND_PORT = int(os.getenv("CLIENT_BACKEND_PORT", "8004"))
    SSO_JWKS_URL = os.getenv("SSO_JWKS_URL", "")


settings = Settings()
