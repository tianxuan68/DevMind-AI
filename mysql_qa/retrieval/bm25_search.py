"""BM25 FAQ 检索（T5）。

对外接口：faq_match(query: str) -> FAQHit | None
参考基线：E:/study_project/Itcast_qa_system/mysql_qa/retrieval/bm25_search.py
"""
# TODO(T5 算法组): 低于置信度阈值返回 None，走 RAG 主链路。
class BM25Search:
    def __init__(self, redis_client=None, mysql_client=None):
        raise NotImplementedError("TODO(T5): implement BM25 FAQ search")
