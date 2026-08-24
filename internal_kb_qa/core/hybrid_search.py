"""T4 BM25 + Dense 混合检索（RRF 融合）。

对外接口：
    search(query: str, top_k: int, filter: dict = None) -> list[Hit]
"""
# TODO(T4 算法组): Milvus hybrid search；filter 必须注入 team/system/security_level。

# -*- coding: utf-8 -*-
"""
混合检索模块（Hybrid Retrieval with Rerank）
功能：基于 BGE-M3 的稠密+稀疏混合检索 + BGE-Reranker 重排序
"""

import os

# 限制 BLAS 线程，避免 Windows 下多进程/多实例加载模型时内存暴涨
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")

import time
import torch.cuda
from langchain_core.documents import Document
from pymilvus import MilvusClient, AnnSearchRequest, WeightedRanker
from milvus_model.hybrid import BGEM3EmbeddingFunction

from base.config import Config
from base.logger import logger
from internal_kb_qa.core.hit import Hit
from internal_kb_qa.core.milvus_paths import build_file_path_filter

conf = Config()


def _hit_score(raw_hit: dict) -> float:
    for key in ("distance", "score", "_distance"):
        if key in raw_hit and raw_hit[key] is not None:
            try:
                return float(raw_hit[key])
            except (TypeError, ValueError):
                continue
    return 0.0


def _combine_filter_expr(source_filter: str | None, file_paths: list[str] | None) -> str:
    parts: list[str] = []
    if source_filter:
        safe = str(source_filter).replace("\\", "\\\\").replace("'", "\\'")
        parts.append(f"source == '{safe}'")
    path_expr = build_file_path_filter(file_paths or [])
    if path_expr:
        parts.append(f"({path_expr})")
    if not parts:
        return ""
    return " and ".join(parts)


class HybridRetriever:
    """混合检索器"""

    def __init__(self):
        current_dir = os.path.dirname(os.path.abspath(__file__))
        self.rag_qa_path = os.path.dirname(current_dir)

        self.device = 'cuda' if torch.cuda.is_available() else 'cpu'
        logger.info(f"设备: {self.device}")

        m3_path = os.path.join(self.rag_qa_path, 'models', 'bge-m3')
        logger.info(f"加载 BGE-M3: {m3_path}")
        start = time.time()
        self.embedding_function = BGEM3EmbeddingFunction(
            model_name_or_path=m3_path,
            use_fp16=(self.device == 'cuda'),
            device=self.device
        )
        logger.info(f"BGE-M3 加载完成，耗时: {time.time() - start:.2f}s")

        host = conf.MILVUS_HOST
        port = conf.MILVUS_PORT
        database = conf.MILVUS_DATABASE_NAME

        logger.info(f"连接 Milvus: http://{host}:{port}/{database}")
        self.client = MilvusClient(uri=f"http://{host}:{port}", db_name=database)
        logger.info("Milvus 连接成功")

    def doc_from_hit(self, hit: dict, score: float) -> Document:
        entity = hit.get("entity")
        payload = entity if isinstance(entity, dict) and entity else hit
        meta = {
            "parent_id": payload.get("parent_id"),
            "parent_content": payload.get("parent_content"),
            "source": payload.get("source"),
            "timestamp": payload.get("timestamp"),
            "file_path": payload.get("file_path"),
            "title": payload.get("title"),
            "child_id": payload.get("id") or hit.get("id"),
            "matched_child_text": payload.get("text"),
            "milvus_score": score,
        }
        return Document(
            page_content=payload.get("parent_content") or payload.get("text") or "",
            metadata=meta,
        )

    def get_unique_parent_docs(self, scored_chunks: list[tuple[float, Document]]) -> list[Document]:
        """按父块去重，保留 Milvus 分数最高的子块作为命中代表。"""
        best: dict[str, tuple[float, Document]] = {}
        for score, chunk in scored_chunks:
            parent_id = chunk.metadata.get("parent_id") or chunk.metadata.get("child_id") or ""
            key = parent_id or chunk.page_content[:80]
            if key not in best or score > best[key][0]:
                best[key] = (score, chunk)

        unique_docs: list[Document] = []
        for score, chunk in best.values():
            chunk.metadata["score"] = score
            unique_docs.append(chunk)
        unique_docs.sort(key=lambda d: float(d.metadata.get("score", 0)), reverse=True)
        return unique_docs

    def search(
        self,
        query,
        k=conf.TOP_K,
        source_filter=None,
        file_paths: list[str] | None = None,
        mode: str = "hybrid",
        use_rerank: bool = True,
    ):
        total_start = time.time()
        logger.info(f"查询: {query[:80]}{'...' if len(query) > 80 else ''}")
        logger.info(
            "参数: k=%s, source_filter=%s, file_paths=%s, mode=%s, use_rerank=%s",
            k, source_filter, len(file_paths or []), mode, use_rerank,
        )

        embed_start = time.time()
        query_embeddings = self.embedding_function([query])
        dense_query_vector = query_embeddings["dense"][0]
        logger.info(f"向量生成耗时: {time.time() - embed_start:.3f}s")

        sparse_query_vector = {}
        try:
            row = query_embeddings["sparse"][0]
            if hasattr(row, 'col'):
                indices = row.col
                values = row.data
            else:
                indices = row.indices
                values = row.data
        except Exception:
            row = query_embeddings["sparse"].getrow(0)
            indices = row.indices
            values = row.data

        for idx, value in zip(indices, values):
            sparse_query_vector[idx] = value

        filter_expr = _combine_filter_expr(source_filter, file_paths)
        output_fields = ["id", "text", "parent_id", "parent_content", "source", "timestamp", "file_path", "title"]
        recall_k = max(k * 4, 20) if file_paths else max(k * 2, 10)

        search_start = time.time()
        if mode == "dense":
            raw_results = self.client.search(
                collection_name=conf.MILVUS_COLLECTION_NAME,
                data=[dense_query_vector],
                anns_field="dense_vector",
                search_params={"metric_type": "IP", "params": {"nprobe": 10}},
                filter=filter_expr or None,
                limit=recall_k,
                output_fields=output_fields,
            )
            hits = raw_results[0] if raw_results else []
        elif mode == "sparse":
            raw_results = self.client.search(
                collection_name=conf.MILVUS_COLLECTION_NAME,
                data=[sparse_query_vector],
                anns_field="sparse_vector",
                search_params={"metric_type": "IP", "params": {}},
                filter=filter_expr or None,
                limit=recall_k,
                output_fields=output_fields,
            )
            hits = raw_results[0] if raw_results else []
        else:
            dense_request = AnnSearchRequest(
                data=[dense_query_vector],
                anns_field="dense_vector",
                param={"metric_type": "IP", "params": {"nprobe": 10}},
                limit=recall_k,
                expr=filter_expr or None,
            )
            sparse_request = AnnSearchRequest(
                data=[sparse_query_vector],
                anns_field="sparse_vector",
                param={"metric_type": "IP", "params": {}},
                limit=recall_k,
                expr=filter_expr or None,
            )
            ranker = WeightedRanker(0.7, 0.3)
            hits = self.client.hybrid_search(
                collection_name=conf.MILVUS_COLLECTION_NAME,
                reqs=[dense_request, sparse_request],
                ranker=ranker,
                limit=recall_k,
                output_fields=output_fields,
            )[0]
        logger.info(f"检索耗时: {time.time() - search_start:.3f}s, 返回 {len(hits)} 条")

        scored_chunks: list[tuple[float, Document]] = []
        for hit in hits:
            if not isinstance(hit, dict):
                continue
            score = _hit_score(hit)
            entity = hit.get("entity")
            payload = entity if isinstance(entity, dict) and entity else hit
            if payload.get("text"):
                scored_chunks.append((score, self.doc_from_hit(hit, score)))

        parent_docs = self.get_unique_parent_docs(scored_chunks)
        logger.info(f"去重后父文档数: {len(parent_docs)}")

        if len(parent_docs) < 2 or not use_rerank:
            logger.info("跳过重排序: docs=%s use_rerank=%s", len(parent_docs), use_rerank)
            return parent_docs[:k]

        from internal_kb_qa.core.reranker import rerank

        hits_for_rerank = [
            Hit(
                text=doc.page_content,
                score=float(doc.metadata.get("score", 0.5)),
                metadata=doc.metadata,
            )
            for doc in parent_docs
        ]
        try:
            ranked_hits = rerank(query, hits_for_rerank, top_k=k)
        except Exception as exc:
            logger.warning("Reranker 不可用，使用 Milvus 分数排序: %s", exc)
            return parent_docs[:k]

        final_docs: list[Document] = []
        for hit in ranked_hits:
            final_docs.append(
                Document(page_content=hit.text, metadata={**hit.metadata, "score": hit.score})
            )
        logger.info(f"最终返回 {len(final_docs)} 个文档, 总耗时: {time.time() - total_start:.3f}s")
        return final_docs


_retriever: HybridRetriever | None = None


def warmup() -> None:
    """启动预热：加载 BGE-M3 与 Milvus 连接。"""
    global _retriever
    if _retriever is None:
        _retriever = HybridRetriever()
    logger.info("混合检索模块预热完成")


def search(
    query: str,
    top_k: int,
    filter: dict | None = None,
    mode: str = "hybrid",
    use_rerank: bool = True,
) -> list[Hit]:
    """BM25 + Dense 混合检索（T4 对外接口）。"""
    global _retriever
    try:
        if _retriever is None:
            _retriever = HybridRetriever()
    except Exception:
        _retriever = None
        raise

    filter = filter or {}
    source_filter = filter.get("source") or filter.get("system") or filter.get("team")
    file_paths = filter.get("file_paths")

    docs = _retriever.search(
        query,
        k=top_k,
        source_filter=source_filter,
        file_paths=file_paths,
        mode=mode,
        use_rerank=use_rerank,
    )
    return [
        Hit(
            text=doc.page_content,
            score=float(doc.metadata.get("score", 0.5)),
            metadata=doc.metadata,
        )
        for doc in docs
    ]


if __name__ == "__main__":
    retriever = HybridRetriever()
    query = "AI学科学费是多少？"
    results = retriever.search(query, source_filter='ai')
    print(f'results-->{results}')
    print(f'results-->{len(results)}')
