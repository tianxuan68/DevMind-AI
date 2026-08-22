"""mysql_qa：高频 FAQ 精确匹配模块（T5）。

参考基线：E:/study_project/Itcast_qa_system/mysql_qa/
"""
try:
    import base.logger  # noqa: F401  确保控制台+文件日志已初始化
except Exception:  # pragma: no cover - 独立运行 mysql_qa 时允许不依赖 base
    pass

from .db.mysql_client import MySQLClient  # noqa: F401
from .cache.redis_client import RedisClient  # noqa: F401
from .errors import FAQStoreUnavailableError  # noqa: F401
from .retrieval.bm25_search import BM25Search, FAQHit  # noqa: F401
from .sql_main import (  # noqa: F401
    faq_match,
    get_faq_searcher,
    refresh_faq_searcher,
    reset_faq_searcher,
)
