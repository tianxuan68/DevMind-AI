"""T3/T4 Milvus 向量库：建表、写入、查询统计。"""
from __future__ import annotations

import hashlib
import os
from datetime import datetime

import torch.cuda
from langchain_core.documents import Document
from milvus_model.hybrid import BGEM3EmbeddingFunction
from pymilvus import DataType, MilvusClient

from base.config import Config
from base.logger import logger
from internal_kb_qa.core.milvus_paths import build_file_path_filter, canonical_storage_path

conf = Config()


class VectorStore:
    def __init__(
        self,
        collection_name: str | None = None,
        host: str | None = None,
        port: int | None = None,
        database: str | None = None,
    ):
        self.collection_name = collection_name or conf.MILVUS_COLLECTION_NAME
        self.host = host or conf.MILVUS_HOST
        self.port = port or conf.MILVUS_PORT
        self.database = database or conf.MILVUS_DATABASE_NAME
        self.device = "cuda" if torch.cuda.is_available() else "cpu"

        current_dir = os.path.dirname(os.path.abspath(__file__))
        rag_root = os.path.dirname(current_dir)
        m3_path = os.path.join(rag_root, "models", "bge-m3")
        logger.info("加载 BGE-M3: %s (device=%s)", m3_path, self.device)
        self.embedding_function = BGEM3EmbeddingFunction(
            model_name_or_path=m3_path,
            use_fp16=(self.device == "cuda"),
            device=self.device,
        )
        self.dense_dim = self.embedding_function.dim["dense"]
        self._ensure_database()
        self.client = MilvusClient(uri=f"http://{self.host}:{self.port}", db_name=self.database)
        self._create_or_load_collection()

    def _ensure_database(self) -> None:
        admin = MilvusClient(uri=f"http://{self.host}:{self.port}")
        databases = set(admin.list_databases())
        if self.database not in databases:
            admin.create_database(self.database)
            logger.info("已创建 Milvus 数据库: %s", self.database)

    def _create_or_load_collection(self) -> None:
        if not self.client.has_collection(self.collection_name):
            schema = self.client.create_schema(auto_id=False, enable_dynamic_field=True)
            schema.add_field(field_name="id", datatype=DataType.VARCHAR, is_primary=True, max_length=100)
            schema.add_field(field_name="text", datatype=DataType.VARCHAR, max_length=65535)
            schema.add_field(field_name="dense_vector", datatype=DataType.FLOAT_VECTOR, dim=self.dense_dim)
            schema.add_field(field_name="sparse_vector", datatype=DataType.SPARSE_FLOAT_VECTOR)
            schema.add_field(field_name="parent_id", datatype=DataType.VARCHAR, max_length=100)
            schema.add_field(field_name="parent_content", datatype=DataType.VARCHAR, max_length=65535)
            schema.add_field(field_name="source", datatype=DataType.VARCHAR, max_length=50)
            schema.add_field(field_name="timestamp", datatype=DataType.VARCHAR, max_length=50)

            index_params = self.client.prepare_index_params()
            index_params.add_index(
                field_name="dense_vector",
                index_name="dense_index",
                index_type="IVF_FLAT",
                metric_type="IP",
                params={"nlist": 128},
            )
            index_params.add_index(
                field_name="sparse_vector",
                index_name="sparse_index",
                index_type="SPARSE_INVERTED_INDEX",
                metric_type="IP",
                params={"drop_ratio_build": 0.2},
            )
            self.client.create_collection(
                collection_name=self.collection_name,
                schema=schema,
                index_params=index_params,
            )
            logger.info("已创建 Milvus 集合: %s", self.collection_name)
        else:
            logger.info("已加载 Milvus 集合: %s", self.collection_name)
        self.client.load_collection(self.collection_name)

    def drop_collection(self) -> None:
        if self.client.has_collection(self.collection_name):
            self.client.drop_collection(self.collection_name)
            logger.info("已删除 Milvus 集合: %s", self.collection_name)

    def count(self) -> int:
        stats = self.client.get_collection_stats(self.collection_name)
        return int(stats.get("row_count", 0))

    def delete_by_storage_paths(self, storage_paths: list[str]) -> int:
        """按文档 storage_path 删除 Milvus 中对应子块（含路径变体）。"""
        if not storage_paths:
            return 0
        if not self.client.has_collection(self.collection_name):
            return 0

        expr = build_file_path_filter(storage_paths)
        if not expr:
            return 0

        try:
            result = self.client.delete(collection_name=self.collection_name, filter=expr)
            self.client.flush(self.collection_name)
            deleted = int(result.get("delete_count", 0) if isinstance(result, dict) else 0)
            logger.info("Milvus 删除切块 paths=%s count=%s", len(storage_paths), deleted)
            return deleted
        except Exception as exc:
            logger.warning("Milvus 删除切块失败: %s", exc)
            return 0

    def insert(self, chunks: list[Document]) -> int:
        if not chunks:
            return 0
        texts = [doc.page_content for doc in chunks]
        embeddings = self.embedding_function(texts)
        rows = []
        for index, doc in enumerate(chunks):
            sparse_vector = {}
            row = embeddings["sparse"][index]
            if hasattr(row, "col"):
                indices, values = row.col, row.data
            else:
                indices, values = row.indices, row.data
            for token_id, value in zip(indices, values):
                sparse_vector[int(token_id)] = float(value)

            chunk_id = doc.metadata.get("id") or hashlib.md5(doc.page_content.encode("utf-8")).hexdigest()
            rows.append(
                {
                    "id": chunk_id,
                    "text": doc.page_content,
                    "dense_vector": embeddings["dense"][index],
                    "sparse_vector": sparse_vector,
                    "parent_id": doc.metadata.get("parent_id", chunk_id),
                    "parent_content": doc.metadata.get("parent_content", doc.page_content),
                    "source": doc.metadata.get("source", "unknown"),
                    "timestamp": doc.metadata.get("timestamp", datetime.now().isoformat()),
                    "file_path": canonical_storage_path(doc.metadata.get("file_path", "")) if doc.metadata.get("file_path") else "",
                    "title": str(doc.metadata.get("title", "")),
                }
            )
        self.client.upsert(collection_name=self.collection_name, data=rows)
        self.client.flush(self.collection_name)
        logger.info("已向 Milvus 写入 %s 条子块", len(rows))
        return len(rows)
