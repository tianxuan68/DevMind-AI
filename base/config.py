"""配置加载模块。

参考基线：E:/study_project/Itcast_qa_system/base/config.py
"""
import ast
import configparser
import os


class Config:
    """加载 config.ini 并暴露 MySQL/Redis/Milvus/LLM/安全/检索配置。"""

    def __init__(self, config_file: str = "config.ini"):
        self.config = configparser.ConfigParser()
        self.config.read(config_file, encoding="utf-8")

        self.MYSQL_HOST = os.getenv("MYSQL_HOST") or self.config.get("mysql", "host", fallback="localhost")
        self.MYSQL_USER = os.getenv("MYSQL_USER") or self.config.get("mysql", "user", fallback="root")
        self.MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD") or self.config.get("mysql", "password", fallback="")
        self.MYSQL_DATABASE = os.getenv("MYSQL_DATABASE") or self.config.get("mysql", "database", fallback="internal_tech_kb")

        self.REDIS_HOST = os.getenv("REDIS_HOST") or self.config.get("redis", "host", fallback="localhost")
        redis_port = os.getenv("REDIS_PORT")
        self.REDIS_PORT = int(redis_port) if redis_port else self.config.getint("redis", "port", fallback=16379)
        self.REDIS_PASSWORD = os.getenv("REDIS_PASSWORD") or self.config.get("redis", "password", fallback="")
        redis_db = os.getenv("REDIS_DB")
        self.REDIS_DB = int(redis_db) if redis_db else self.config.getint("redis", "db", fallback=0)

        self.MILVUS_HOST = os.getenv("MILVUS_HOST") or self.config.get("milvus", "host", fallback="localhost")
        milvus_port = os.getenv("MILVUS_PORT")
        self.MILVUS_PORT = int(milvus_port) if milvus_port else self.config.getint("milvus", "port", fallback=19530)
        self.MILVUS_DATABASE_NAME = self.config.get("milvus", "database_name", fallback="internal_tech_kb")
        self.MILVUS_COLLECTION_NAME = self.config.get("milvus", "collection_name", fallback="internal_tech_kb")

        self.LLM_MODEL = self.config.get("llm", "model", fallback="qwen-plus")
        self.DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY") or self.config.get("llm", "dashscope_api_key", fallback="")
        self.DASHSCOPE_BASE_URL = self.config.get("llm", "dashscope_base_url", fallback="https://dashscope.aliyuncs.com/compatible-mode/v1")

        self.BGE_MODEL = self.config.get("embedding", "model_name", fallback="bge-m3")
        self.BGE_DIM = self.config.getint("embedding", "dim", fallback=1024)
        self.RERANKER_MODEL = self.config.get("reranker", "model_name", fallback="bge-reranker-v2-m3")

        self.CHUNK_SIZE = self.config.getint("retrieval", "chunk_size", fallback=1200)
        self.PARENT_CHUNK_SIZE = self.config.getint("retrieval", "parent_chunk_size", fallback=1200)
        self.CHILD_CHUNK_SIZE = self.config.getint("retrieval", "child_chunk_size", fallback=300)
        self.CHUNK_OVERLAP = self.config.getint("retrieval", "chunk_overlap", fallback=150)
        self.TOP_K = self.config.getint("retrieval", "top_k", fallback=5)
        self.RERANK_TOP_K = self.config.getint("retrieval", "rerank_top_k", fallback=3)
        self.CANDIDATE_M = self.config.getint("retrieval", "candidate_m", fallback=3)
        self.CONFIDENCE_THRESHOLD = self.config.getfloat("retrieval", "confidence_threshold", fallback=0.75)
        self.ANSWER_CACHE_TTL = self.config.getint("retrieval", "answer_cache_ttl", fallback=3600)

        self.APP_PORT = self.config.getint("app", "port", fallback=8003)
        self.VALID_SOURCES = ast.literal_eval(
            self.config.get("app", "valid_sources", fallback='["infra", "backend", "frontend", "data", "ops"]')
        )
        self.LOG_FILE = self.config.get("logger", "log_file", fallback="logs/app.log")

        self.SSO_MODE = os.getenv("SSO_MODE") or self.config.get("security", "sso_mode", fallback="mock")
        self.SSO_TOKEN_HEADER = self.config.get("security", "sso_token_header", fallback="Authorization")
        # 与工作台 JWT 共用密钥：优先 JWT_SECRET，便于登录态直连 /api/query、/api/stream
        self.SSO_SECRET = (
            os.getenv("JWT_SECRET")
            or os.getenv("SSO_SECRET")
            or self.config.get("security", "sso_secret", fallback="devmind-ai-sso-secret")
        )
        self.DEFAULT_SECURITY_LEVEL = self.config.get("security", "default_security_level", fallback="team")

        self.TICKET_ENABLED = self.config.getboolean("ticket", "enabled", fallback=True)
        self.TICKET_EXTERNAL_ENABLED = self.config.getboolean("ticket", "external_enabled", fallback=False)
        self.TICKET_EXTERNAL_API_URL = self.config.get("ticket", "external_api_url", fallback="")
        self.TICKET_QUEUE_KEY = self.config.get("ticket", "queue_key", fallback="ticket:queue")
