"""Milvus 向量库：BGE-M3 向量化并写入 internal_tech_kb。"""
import hashlib
import json
import logging
import os
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional

from .models import Chunk

logger = logging.getLogger(__name__)

_REQUIRED_META_KEYS = ("team", "system", "version", "last_updated", "security_level")


def _load_config() -> Any:
    """从项目根目录加载 config.ini。"""
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    from base.config import Config

    config_path = os.path.join(project_root, "config.ini")
    return Config(config_path)


def _chunk_id(text: str, metadata: Dict[str, Any]) -> str:
    payload = json.dumps(
        {"text": text, "source": metadata.get("source"), "page": metadata.get("page")},
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.md5(payload.encode("utf-8")).hexdigest()


class VectorStore:
    """BGE-M3 Embedding + Milvus 稠密向量入库。"""

    def __init__(
        self,
        collection_name: Optional[str] = None,
        host: Optional[str] = None,
        port: Optional[int] = None,
        database: Optional[str] = None,
        embedding_model: Optional[str] = None,
        dense_dim: Optional[int] = None,
    ):
        config = _load_config()
        self.collection_name = collection_name or config.MILVUS_COLLECTION_NAME
        self.host = host or config.MILVUS_HOST
        self.port = int(port or config.MILVUS_PORT)
        self.database = database or config.MILVUS_DATABASE_NAME
        self.dense_dim = dense_dim or config.BGE_DIM
        self.embedding_model = embedding_model or config.BGE_MODEL

        self._client = None
        self._embedding_fn = None
        self._initialized = False

    def _ensure_client(self) -> None:
        if self._client is not None:
            return
        from pymilvus import MilvusClient

        uri = f"http://{self.host}:{self.port}"
        self._client = MilvusClient(uri=uri, db_name=self.database)
        self._create_or_load_collection()

    def _ensure_embedding(self) -> None:
        if self._embedding_fn is not None:
            return
        try:
            from milvus_model.hybrid import BGEM3EmbeddingFunction

            self._embedding_fn = BGEM3EmbeddingFunction(
                model_name="BAAI/bge-m3",
                use_fp16=False,
                device="cpu",
            )
            self.dense_dim = self._embedding_fn.dim["dense"]
        except Exception as exc:
            logger.warning("BGEM3EmbeddingFunction 不可用，回退 sentence-transformers: %s", exc)
            from sentence_transformers import SentenceTransformer

            model_name = self.embedding_model
            if "/" not in model_name:
                model_name = f"BAAI/{model_name}"
            model = SentenceTransformer(model_name)
            self.dense_dim = model.get_sentence_embedding_dimension()

            class _FallbackEmbedding:
                def __init__(self, encoder):
                    self.encoder = encoder

                def __call__(self, texts: List[str]) -> Dict[str, Any]:
                    vectors = self.encoder.encode(texts, normalize_embeddings=True)
                    return {"dense": vectors}

            self._embedding_fn = _FallbackEmbedding(model)

    def _create_or_load_collection(self) -> None:
        from pymilvus import DataType

        if self._client.has_collection(self.collection_name):
            self._client.load_collection(self.collection_name)
            self._initialized = True
            return

        schema = self._client.create_schema(auto_id=False, enable_dynamic_field=True)
        schema.add_field("id", DataType.VARCHAR, is_primary=True, max_length=64)
        schema.add_field("text", DataType.VARCHAR, max_length=65535)
        schema.add_field("dense_vector", DataType.FLOAT_VECTOR, dim=self.dense_dim)
        schema.add_field("source", DataType.VARCHAR, max_length=256)
        schema.add_field("page", DataType.INT64)
        schema.add_field("doc_type", DataType.VARCHAR, max_length=32)
        schema.add_field("team", DataType.VARCHAR, max_length=64)
        schema.add_field("system", DataType.VARCHAR, max_length=64)
        schema.add_field("version", DataType.VARCHAR, max_length=32)
        schema.add_field("last_updated", DataType.VARCHAR, max_length=64)
        schema.add_field("security_level", DataType.VARCHAR, max_length=32)
        schema.add_field("chunk_type", DataType.VARCHAR, max_length=16)
        schema.add_field("metadata_json", DataType.VARCHAR, max_length=4096)
        schema.add_field("timestamp", DataType.VARCHAR, max_length=64)

        index_params = self._client.prepare_index_params()
        index_params.add_index(
            field_name="dense_vector",
            index_name="dense_index",
            index_type="IVF_FLAT",
            metric_type="IP",
            params={"nlist": 128},
        )

        self._client.create_collection(
            collection_name=self.collection_name,
            schema=schema,
            index_params=index_params,
        )
        self._client.load_collection(self.collection_name)
        self._initialized = True
        logger.info("已创建 Milvus collection: %s", self.collection_name)

    def insert(self, chunks: List[Chunk]) -> int:
        """将 Chunk 列表向量化并写入 Milvus，返回成功条数。"""
        if not chunks:
            return 0

        self._ensure_embedding()
        self._ensure_client()

        texts = [chunk.text for chunk in chunks]
        embeddings = self._embedding_fn(texts)
        dense_vectors = embeddings["dense"]

        rows: List[Dict[str, Any]] = []
        now = datetime.now().isoformat(timespec="seconds")

        for index, chunk in enumerate(chunks):
            meta = dict(chunk.metadata)
            for key in _REQUIRED_META_KEYS:
                meta.setdefault(key, "unknown")

            row = {
                "id": _chunk_id(chunk.text, meta),
                "text": chunk.text,
                "dense_vector": dense_vectors[index],
                "source": str(meta.get("source", "")),
                "page": int(meta.get("page", 1) or 1),
                "doc_type": str(meta.get("doc_type", "")),
                "team": str(meta.get("team", "")),
                "system": str(meta.get("system", "")),
                "version": str(meta.get("version", "")),
                "last_updated": str(meta.get("last_updated", "")),
                "security_level": str(meta.get("security_level", "")),
                "chunk_type": str(meta.get("chunk_type", "text")),
                "metadata_json": json.dumps(meta, ensure_ascii=False),
                "timestamp": now,
            }
            rows.append(row)

        self._client.upsert(collection_name=self.collection_name, data=rows)
        logger.info("成功写入 %d 条 chunk 到 %s", len(rows), self.collection_name)
        return len(rows)
