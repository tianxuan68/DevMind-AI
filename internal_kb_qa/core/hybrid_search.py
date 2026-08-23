"""T4 BM25 + Dense 混合检索（RRF 融合）。

对外接口（契约，见 docs/企业内部技术知识库智能问答系统-任务分工.md T4 节）：
    search(query: str, top_k: int, filter: dict = None) -> list[Hit]

说明：
    - 本模块只做「混合召回」（BGE-M3 稠密 + 稀疏，Milvus hybrid_search + 加权融合）。
    - 精排由 T7 reranker.py 的 rerank() 负责，本模块不重排。
    - filter 用于强制注入权限过滤（team / system / security_level），不可绕过。
"""
from __future__ import annotations

import time
from pathlib import Path

import torch
from milvus_model.hybrid import BGEM3EmbeddingFunction
from pymilvus import AnnSearchRequest, MilvusClient, WeightedRanker

from base.config import Config
from base.logger import logger
from internal_kb_qa.core.hit import Hit

conf = Config()

# 命中文档需要带回的元数据字段（与 T3 入库时写入 collection 的字段一致）
METADATA_FIELDS = (
    "source", "page", "doc_type",
    "team", "system", "version", "last_updated", "security_level",
)
OUTPUT_FIELDS = ["text", *METADATA_FIELDS]

# 稠密 / 稀疏融合权重（Milvus v2.3 只支持 WeightedRanker；v2.4+ 可换 RRFRanker 实现真 RRF）
_DENSE_WEIGHT = 0.5
_SPARSE_WEIGHT = 0.5


def _models_dir() -> Path:
    """模型目录：internal_kb_qa/models/。"""
    return Path(__file__).resolve().parents[1] / "models"


def _build_filter_expr(filter: dict | None) -> str | None:
    """把权限/元数据过滤 dict 转成 Milvus filter 表达式。

    例：{"team": "backend", "security_level": "team"} -> "team == 'backend' and security_level == 'team'"
    """
    if not filter:
        return None
    parts = []
    for key in ("team", "system", "security_level", "doc_type", "source"):
        value = filter.get(key)
        if value is None or value == "":
            continue
        if isinstance(value, (list, tuple, set)):
            # 多值过滤：in ['a', 'b']
            quoted = ", ".join(f"'{v}'" for v in value)
            parts.append(f"{key} in [{quoted}]")
        else:
            parts.append(f"{key} == '{value}'")
    return " and ".join(parts) or None


class HybridRetriever:
    """BGE-M3 稠密 + 稀疏混合检索（进程内单例，避免重复加载模型）。"""

    _instance: HybridRetriever | None = None

    def __init__(self) -> None:
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        logger.info("T4 混合检索设备: %s", self.device)

        m3_path = _models_dir() / "bge-m3"
        logger.info("加载 BGE-M3: %s", m3_path)
        start = time.time()
        self.embedding_function = BGEM3EmbeddingFunction(
            model_name_or_path=str(m3_path),
            use_fp16=(self.device == "cuda"),
            device=self.device,
        )
        logger.info("BGE-M3 加载完成，耗时: %.2fs", time.time() - start)

        uri = f"http://{conf.MILVUS_HOST}:{conf.MILVUS_PORT}"
        logger.info("连接 Milvus: %s/%s", uri, conf.MILVUS_DATABASE_NAME)
        self.client = MilvusClient(uri=uri, db_name=conf.MILVUS_DATABASE_NAME)
        logger.info("Milvus 连接成功")

    @classmethod
    def get_instance(cls) -> "HybridRetriever":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def search(self, query: str, k: int | None = None, filter: dict | None = None) -> list[Hit]:
        """执行混合召回，返回 Hit 列表（含 RRF/加权融合得分）。"""
        k = k or conf.TOP_K
        total_start = time.time()
        logger.info("T4 检索: %s, k=%d, filter=%s", query[:80], k, filter)

        # 1) 生成稠密 + 稀疏查询向量
        embed_start = time.time()
        query_embeddings = self.embedding_function([query])
        dense_vec = query_embeddings["dense"][0]
        sparse_vec = query_embeddings["sparse"].getrow(0)
        logger.info("向量生成耗时: %.3fs", time.time() - embed_start)

        # 2) 稠密 + 稀疏双路召回，加权融合
        reqs = [
            AnnSearchRequest(dense_vec, "dense", {"metric_type": "IP"}, limit=k),
            AnnSearchRequest(sparse_vec, "sparse", {"metric_type": "IP"}, limit=k),
        ]
        res = self.client.hybrid_search(
            collection_name=conf.MILVUS_COLLECTION_NAME,
            reqs=reqs,
            ranker=WeightedRanker(_DENSE_WEIGHT, _SPARSE_WEIGHT),
            filter=_build_filter_expr(filter),
            output_fields=OUTPUT_FIELDS,
            limit=k,
        )

        # 3) 组装成契约要求的 list[Hit]
        hits: list[Hit] = []
        for hit in res[0]:
            entity = hit.get("entity", {}) or {}
            metadata = {f: entity[f] for f in METADATA_FIELDS if entity.get(f) not in (None, "")}
            hits.append(Hit(
                text=entity.get("text", ""),
                score=float(hit.get("distance", 0.0)),
                metadata=metadata,
            ))

        logger.info("T4 召回完成: %d 条, 总耗时 %.3fs", len(hits), time.time() - total_start)
        return hits


# ---------------------------------------------------------------------------
# 对外契约：模块级函数（T7 rag_generator 直接 import 这个）
# ---------------------------------------------------------------------------

def search(query: str, top_k: int | None = None, filter: dict | None = None) -> list[Hit]:
    """T4 混合检索契约入口。"""
    return HybridRetriever.get_instance().search(query, k=top_k, filter=filter)
