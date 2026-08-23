"""mysql_qa 自定义异常。"""
from __future__ import annotations


class FAQStoreUnavailableError(RuntimeError):
    """FAQ 数据源（MySQL/Redis）不可用或加载失败。"""
