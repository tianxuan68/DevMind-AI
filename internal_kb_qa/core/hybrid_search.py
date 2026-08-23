# -*- coding: utf-8 -*-
"""
双通道混合检索（Milvus 为主，图导路为辅，含降级机制）
功能：
    - 通道A（主导）：直接用 Query 进行 Milvus 混合检索。
    - 通道B（辅助）：利用图数据库实体匹配获取锚点，再用锚点去 Milvus 检索父块。
    - 降级策略：若 Neo4j 不可用，自动降级为纯 Milvus 检索。
"""

from __future__ import annotations

import csv
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


# 使用 pathlib 动态获取上级目录
base_dir = Path(__file__).resolve().parents[2]  # E:\pythonProject\RAG_project
csv_path = base_dir/ "docs" / "neofj" / "java_manual_edges.csv"
# =====================================================================
# 【新增】自动加载数据集到 Neo4j 的函数（支持动态属性，不固定字段）
# =====================================================================
def load_csv_to_neo4j(csv_path):
    print(f"正在加载数据集: {csv_path} ...")
    if not Path(csv_path).exists():
        print("文件不存在，跳过。")
        return

    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    with driver.session() as session:
        # 创建唯一约束
        session.run("CREATE CONSTRAINT IF NOT EXISTS FOR (n:Node) REQUIRE n.id IS UNIQUE")

        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                from_id = row.get("from_id")
                to_id = row.get("to_id")
                subject = row.get("subject")  # 获取起点名称
                obj = row.get("object")  # 获取终点名称
                relation = row.get("relation")

                # 核心修正：将 subject 和 object 显式映射为 name 属性
                # 其余字段（如果有）可自动作为附加属性
                src_props = {k: v for k, v in row.items() if k not in ["from_id", "to_id"]}
                dst_props = {k: v for k, v in row.items() if k not in ["from_id", "to_id"]}

                # 显式确保 name 属性存在
                src_props["name"] = subject
                dst_props["name"] = obj

                session.run("""
                    MERGE (src:Node {id: $from_id})
                    SET src += $src_props
                    MERGE (dst:Node {id: $to_id})
                    SET dst += $dst_props
                    MERGE (src)-[r:RELATED {relation: $relation}]->(dst)
                """, from_id=from_id, to_id=to_id, relation=relation,
                            src_props=src_props, dst_props=dst_props)

        count = session.run("MATCH (n:Node) RETURN count(n) AS count").single()["count"]
        print(f"加载完成，共 {count} 个节点。")
    driver.close()


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
        # 使用 BGE-M3 嵌入函数生成查询的嵌入
        query_embeddings = self.embedding_function([query])
        # 获取查询的稠密向量
        dense_query_vector = query_embeddings["dense"][0]
        # print(f'dense_query_vector--》{dense_query_vector.shape}')
        # 初始化查询的稀疏向量字典
        sparse_query_vector = {}
        # ====================
        # 获取查询稀疏向量的第 0 行数据
        # row = query_embeddings["sparse"][0]
        # # 获取稀疏向量的非零值索引
        # indices = row.indices
        # # 获取稀疏向量的非零值
        # values = row.data
        # ====================
        try:
            # 新版本 milvus-model 使用 coo_array 格式
            row = query_embeddings["sparse"][0]
            if hasattr(row, 'col'):  # coo_array 格式
                indices = row.col
                values = row.data
            else:  # csr_matrix 格式
                indices = row.indices
                values = row.data
        except Exception as e:
            # 兼容旧版本 milvus-model
            row = query_embeddings["sparse"].getrow(0)
            indices = row.indices
            values = row.data

        # 将索引和值配对，填充稀疏向量字典
        for idx, value in zip(indices, values):
            sparse_query_vector[idx] = value
        # print(f'sparse_query_vector-->{sparse_query_vector}')
        # 初始化过滤表达式，默认不过滤
        filter_expr = _build_filter_expr(filter)        # print(f'filter_expr--》{filter_expr}')
        # 创建稠密向量搜索请求
        dense_request = AnnSearchRequest(
            data=[dense_query_vector],
            anns_field="dense_vector",
            param={"metric_type": "IP", "params": {"nprobe": 10}},
            limit=k,
            expr=filter_expr
        )
        # 创建稀疏向量搜索请求
        sparse_request = AnnSearchRequest(
            data=[sparse_query_vector],
            anns_field="sparse_vector",
            param={"metric_type": "IP", "params": {}},
            limit=k,
            expr=filter_expr
        )

        # 创建加权排序器，稀疏向量权重 0.3，稠密向量权重 0.7
        ranker = WeightedRanker(0.7, 0.3)
        # 执行混合搜索，返回 Top-K 结果
        res = self.milvus_client.hybrid_search(
            collection_name=conf.MILVUS_COLLECTION_NAME,
            reqs=[dense_request, sparse_request],
            ranker=ranker,
            limit=k,
            output_fields=["text", "parent_id", "parent_content", "source", "timestamp"]
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
        # ===== 新增：自动加载数据集判断逻辑 =====
        if self.neo4j_driver is not None and not self._all_node_names:
            logger.info("Neo4j 数据为空，正在自动加载数据集...")
            load_csv_to_neo4j(csv_path)
            # 加载完毕后重新刷新缓存
            with self.neo4j_driver.session() as session:
                result = session.run("MATCH (n:Node) RETURN n.name AS name")
                self._all_node_names = [record["name"] for record in result if record["name"]]
        # ==============================================

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