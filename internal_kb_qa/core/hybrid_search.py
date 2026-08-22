"""T4 BM25 + Dense 混合检索（RRF 融合）。

对外接口：
    search(query: str, top_k: int, filter: dict = None) -> list[Hit]
"""
# TODO(T4 算法组): Milvus hybrid search；filter 必须注入 team/system/security_level。
