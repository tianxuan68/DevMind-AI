# -*- coding: utf-8 -*-
"""
双通道混合检索（Milvus 为主，图导路为辅，含降级机制）
功能：
    - 通道A（主导）：直接用 Query 进行 Milvus 混合检索。
    - 通道B（辅助）：利用图数据库实体匹配获取锚点，再用锚点去 Milvus 检索父块。
    - 降级策略：若 Neo4j 不可用，自动降级为纯 Milvus 检索。
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import torch
import scipy.sparse as sp  # 新增：用于处理稀疏向量兼容性
from pymilvus import MilvusClient, AnnSearchRequest, WeightedRanker
from milvus_model.hybrid import BGEM3EmbeddingFunction
from neo4j import GraphDatabase

from base.config import Config
from base.logger import logger
from internal_kb_qa.core.hit import Hit

conf = Config()

# ================================
# Neo4j 硬编码配置
# ================================
NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "password123"

# ================================
# 大模型配置 (预留，当前逻辑未调用)
# ================================
from langchain_openai import ChatOpenAI

llm = ChatOpenAI(
    model="qwen-max",
    api_key=os.getenv("DASHSCOPE_API_KEY"),
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    temperature=0
)

METADATA_FIELDS = ("source", "page", "doc_type", "team", "system", "version", "last_updated", "security_level",
                   "parent_id", "parent_content")
OUTPUT_FIELDS = ["text", *METADATA_FIELDS]
_DENSE_WEIGHT = 0.5
_SPARSE_WEIGHT = 0.5


def _build_filter_expr(filter: dict | None) -> str | None:
    if not filter:
        return None
    parts = []
    for key in ("team", "system", "security_level", "doc_type", "source"):
        value = filter.get(key)
        if value is None or value == "":
            continue
        if isinstance(value, (list, tuple, set)):
            quoted = ", ".join(f"'{v}'" for v in value)
            parts.append(f"{key} in [{quoted}]")
        else:
            parts.append(f"{key} == '{value}'")
    return " and ".join(parts) or None


class HybridRetriever:
    _instance: HybridRetriever | None = None

    def __init__(self) -> None:
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        m3_path = Path(__file__).resolve().parents[1] / "models" / "bge-m3"

        self.embedding_function = BGEM3EmbeddingFunction(
            model_name_or_path=str(m3_path),
            use_fp16=(self.device == "cuda"),
            device=self.device,
        )
        uri = f"http://{conf.MILVUS_HOST}:{conf.MILVUS_PORT}"
        self.milvus_client = MilvusClient(uri=uri, db_name=conf.MILVUS_DATABASE_NAME)
        logger.info("Milvus 连接成功")

        try:
            self.neo4j_driver = GraphDatabase.driver(
                NEO4J_URI,
                auth=(NEO4J_USER, NEO4J_PASSWORD)
            )
            self.neo4j_driver.verify_connectivity()
            logger.info("Neo4j 连接成功")

            # 加载图库中所有节点名称存入缓存
            with self.neo4j_driver.session() as session:
                result = session.run("MATCH (n:Node) RETURN n.name AS name")
                self._all_node_names = [record["name"] for record in result if record["name"]]
            logger.info(f"成功加载图库节点数: {len(self._all_node_names)}")

        except Exception as e:
            self.neo4j_driver = None
            self._all_node_names = []
            logger.warning(f"Neo4j 连接失败，图检索功能已自动关闭。")

    # ================= 实体提取方法（图库匹配） =================
    def _extract_entities_from_llm(self, query: str) -> list[str]:
        """
        获取图数据库中的所有节点，与query进行字符串匹配，输出匹配成功的实体节点。
        """
        if self.neo4j_driver is None or not self._all_node_names:
            return []

        matched_entities = []
        for node_name in self._all_node_names:
            if not node_name:
                continue
            if len(node_name) >= 2 and (node_name in query or query in node_name):
                matched_entities.append(node_name)
        return matched_entities[:10]

    # ================= 图锚点获取 =================
    def _graph_anchor_search(self, entities: list[str], k: int = 5) -> list[str]:
        if self.neo4j_driver is None or not entities:
            return []
        anchors = list(set(entities))  # 包含自身
        try:
            cypher_query = """
            MATCH (n:Node)
            WHERE n.name IN $entities
            OPTIONAL MATCH (n)-[r]-(neighbor:Node)
            WITH n, collect(neighbor) as neighbors
            UNWIND [n] + neighbors as node
            RETURN DISTINCT node.name AS related_name
            LIMIT $limit
            """
            with self.neo4j_driver.session() as session:
                result = session.run(cypher_query, entities=entities, limit=k)
                for record in result:
                    if record["related_name"] and record["related_name"] not in anchors:
                        anchors.append(record["related_name"])
        except Exception as e:
            logger.error(f"图检索执行异常，跳过图辅助: {e}")
        return anchors

    # ================= 通用 Milvus 检索方法 =================
    def _retrieve_parents_from_milvus(self, query_text, k, filter) -> list[Hit]:
        query_embeddings = self.embedding_function([query_text])
        dense_vec = query_embeddings["dense"][0]

        # 修复稀疏向量兼容性：强制转换为 csr_matrix 并提取第一行
        sparse_mat = query_embeddings["sparse"]
        sparse_vec = sp.csr_matrix(sparse_mat).getrow(0)

        reqs = [
            AnnSearchRequest(dense_vec, "dense", {"metric_type": "IP"}, limit=k),
            AnnSearchRequest(sparse_vec, "sparse", {"metric_type": "IP"}, limit=k),
        ]
        # 修复变量名：self.client -> self.milvus_client
        res = self.milvus_client.hybrid_search(
            collection_name=conf.MILVUS_COLLECTION_NAME,
            reqs=reqs,
            ranker=WeightedRanker(_DENSE_WEIGHT, _SPARSE_WEIGHT),
            filter=_build_filter_expr(filter),
            output_fields=OUTPUT_FIELDS,
            limit=k,
        )[0]

        hits = []
        # === 统一 Hit 构造逻辑 ===
        for hit in res:
            entity = hit.get("entity", {}) or {}
            metadata = {f: entity[f] for f in METADATA_FIELDS if entity.get(f) not in (None, "")}
            hits.append(Hit(
                text=entity.get("text", ""),
                score=float(hit.get("distance", 0.0)),
                metadata=metadata,
            ))
        return hits

    # ================= 图导路检索 =================
    def _graph_guided_milvus(self, query, k, filter) -> list[Hit]:
        if self.neo4j_driver is None:
            return []
        try:
            # 1. 从图库匹配实体
            entities = self._extract_entities_from_llm(query)
            if not entities:
                return []
            # 2. 实体去图库找精准锚点
            anchors = self._graph_anchor_search(entities)
            if not anchors:
                return []

            graph_hits = []
            seen = set()
            for anchor in anchors:
                anchor_hits = self._retrieve_parents_from_milvus(anchor, k, filter)
                for hit in anchor_hits:
                    if hit.text not in seen:
                        seen.add(hit.text)
                        hit.metadata["retriever"] = "milvus_supplement_via_graph"
                        graph_hits.append(hit)
            # 新增：排序，按照得分从高到低
            graph_hits.sort(key=lambda x: x.score, reverse=True)
            # 新增：截取前 k 个
            return graph_hits[:k]
        except Exception as e:
            logger.error(f"图检索执行异常，降级为纯 Milvus: {e}")
            return []

    # ================= 统一搜索入口（双通道） =================
    def search(self, query: str, k: int | None = None, filter: dict | None = None) -> list[Hit]:
        total_start = time.time()
        k = k or conf.TOP_K
        logger.info(f"启动检索: {query[:80]}, k={k}")

        with ThreadPoolExecutor(max_workers=2) as executor:
            # 通道A：直接 Milvus检索
            future_main = executor.submit(self._retrieve_parents_from_milvus, query, k, filter)
            # 通道B：图导路检索
            future_supp = executor.submit(self._graph_guided_milvus, query, k, filter)

            main_hits = future_main.result()
            try:
                supp_hits = future_supp.result()
            except Exception as e:
                logger.error(f"辅助线程发生未捕获异常，降级为纯 Milvus: {e}")
                supp_hits = []

        # 合并去重：Milvus 为主，图导路为辅
        final_hits = []
        seen_texts = set()

        # 1. 优先放入 Milvus 主导检索的结果
        for hit in main_hits:
            if hit.text not in seen_texts:
                final_hits.append(hit)
                seen_texts.add(hit.text)

        # 2. 再放入图导路补充的结果
        for hit in supp_hits:
            if hit.text not in seen_texts:
                final_hits.append(hit)
                seen_texts.add(hit.text)

        logger.info(
            f"合并完成：主检索 {len(main_hits)} 条，补充 {len(supp_hits)} 条，最终返回 {len(final_hits)} 条，总耗时: {time.time() - total_start:.3f}s")
        return final_hits

    @classmethod
    def get_instance(cls) -> "HybridRetriever":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance


# 对外契约
def search(query: str, top_k: int | None = None, filter: dict | None = None) -> list[Hit]:
    return HybridRetriever.get_instance().search(query, k=top_k, filter=filter)


if __name__ == "__main__":
    print("正在初始化检索器（加载模型、连接 Milvus 和 Neo4j）...")
    retriever = HybridRetriever.get_instance()
    query = "命名风格是什么？"
    filter_dict = {"source": "java_manual"}
    print(f"\n开始检索: '{query}'")
    results = retriever.search(query, k=5, filter=filter_dict)
    print(f"\n检索完成，共返回 {len(results)} 条父块内容:")
    print("-" * 50)
    for i, hit in enumerate(results, 1):
        print(f"【结果 {i}】 (来源: {hit.metadata.get('retriever', 'N/A')}, 得分: {hit.score:.4f})")
        print(f"内容摘要: {hit.text[:100]}...")
        print("-" * 50)