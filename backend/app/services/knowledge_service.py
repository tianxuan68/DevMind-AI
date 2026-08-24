"""知识库与 FAQ 服务。"""
import asyncio
import json
import mimetypes
import re
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import HTTPException, UploadFile
from pymysql.err import IntegrityError

from backend.app.core import cache
from backend.app.core.config import settings
from backend.app.core.db import db
from base.logger import logger

ALLOWED_EXTENSIONS = {".pdf", ".md", ".docx", ".txt"}
STATUS_LABEL = {"processing": "处理中", "indexed": "已索引", "failed": "失败", "active": "正常"}


def _normalize_doc_type(ext: str) -> str:
    doc_type = ext.lstrip(".").lower()
    return "doc" if doc_type == "docx" else doc_type


def _build_upload_doc_source(knowledge_base_id: int, file_name: str) -> str:
    """生成上传文档唯一来源标识，避免跨知识库同名文件触发 uniq_document 冲突。"""
    safe_name = Path(file_name).name
    return f"kb/{knowledge_base_id}/upload/{uuid.uuid4().hex}/{safe_name}"


async def _replace_existing_upload(knowledge_base_id: int, file_name: str, doc_type: str) -> None:
    """同名文档再次上传时，删除同知识库内的旧记录以便覆盖。"""
    row = await db.fetch_one(
        """SELECT id FROM documents
           WHERE knowledge_base_id=%s AND file_name=%s AND doc_type=%s""",
        (knowledge_base_id, file_name, doc_type),
    )
    if row:
        await delete_document(row["id"])


def _format_size(size_bytes: int | None) -> str:
    if not size_bytes:
        return "—"
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes / (1024 * 1024):.1f} MB"


def _doc_type_from_name(name: str) -> str:
    ext = Path(name).suffix.lower()
    mapping = {".pdf": "PDF", ".md": "MD", ".doc": "DOC", ".docx": "DOC", ".txt": "TXT"}
    return mapping.get(ext, "FILE")


def _format_dt(value) -> str:
    if not value:
        return "—"
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M")
    return str(value)


def _display_user(nickname: str | None, username: str | None, *, fallback: str = "未知") -> str:
    return nickname or username or fallback


def _serialize_kb(row: dict) -> dict:
    creator = _display_user(row.get("creator_nickname"), row.get("creator_username"), fallback="系统预置")
    if row.get("created_by") is None:
        creator = "系统预置"
    last_uploader = None
    if row.get("document_count"):
        last_uploader = _display_user(
            row.get("last_uploader_nickname"),
            row.get("last_uploader_username"),
            fallback="—",
        )
    return {
        "id": str(row["id"]),
        "name": row["name"],
        "description": row.get("description") or "",
        "owner": row.get("owner_team") or "未分配",
        "docCount": row.get("document_count") or 0,
        "status": STATUS_LABEL.get(row.get("status"), row.get("status")),
        "updatedAt": _format_dt(row.get("updated_at")),
        "createdBy": creator,
        "createdAt": _format_dt(row.get("created_at")),
        "lastUploader": last_uploader,
        "lastUploadedAt": _format_dt(row.get("last_uploaded_at")) if row.get("last_uploaded_at") else None,
    }


def _serialize_doc(row: dict) -> dict:
    name = row.get("file_name") or row.get("doc_source") or "未命名文档"
    index_status = row.get("index_status") or "indexed"
    return {
        "id": str(row["id"]),
        "kbId": str(row["knowledge_base_id"]) if row.get("knowledge_base_id") else None,
        "name": name,
        "type": _doc_type_from_name(name),
        "size": _format_size(row.get("size_bytes")),
        "status": STATUS_LABEL.get(index_status, index_status),
        "chunkCount": row.get("chunk_count") or 0,
        "uploader": row.get("uploader") or "—",
        "updatedAt": _format_dt(row.get("updated_at")),
    }


# ---------------- 知识库 CRUD ----------------

async def list_knowledge_bases() -> list[dict]:
    rows = await db.fetch_all(
        """SELECT kb.*,
                  COUNT(d.id) AS document_count,
                  cu.nickname AS creator_nickname,
                  cu.username AS creator_username,
                  (
                    SELECT u.nickname
                    FROM documents ld
                    LEFT JOIN users u ON u.id = ld.created_by
                    WHERE ld.knowledge_base_id = kb.id
                    ORDER BY ld.updated_at DESC
                    LIMIT 1
                  ) AS last_uploader_nickname,
                  (
                    SELECT u.username
                    FROM documents ld
                    LEFT JOIN users u ON u.id = ld.created_by
                    WHERE ld.knowledge_base_id = kb.id
                    ORDER BY ld.updated_at DESC
                    LIMIT 1
                  ) AS last_uploader_username,
                  (
                    SELECT MAX(ld.updated_at)
                    FROM documents ld
                    WHERE ld.knowledge_base_id = kb.id
                  ) AS last_uploaded_at
           FROM knowledge_bases kb
           LEFT JOIN documents d ON d.knowledge_base_id = kb.id
           LEFT JOIN users cu ON cu.id = kb.created_by
           GROUP BY kb.id
           ORDER BY kb.id ASC"""
    )
    return [_serialize_kb(row) for row in rows]


async def create_knowledge_base(name: str, description: str | None, owner_team: str | None, user_id: int) -> dict:
    exists = await db.fetch_one("SELECT id FROM knowledge_bases WHERE name=%s", (name,))
    if exists:
        raise HTTPException(status_code=409, detail="知识库名称已存在")
    kb_id = await db.execute_lastrowid(
        """INSERT INTO knowledge_bases (name, description, owner_team, status, created_by)
           VALUES (%s, %s, %s, 'active', %s)""",
        (name, description, owner_team, user_id),
    )
    row = await db.fetch_one(
        """SELECT kb.*, 0 AS document_count,
                  cu.nickname AS creator_nickname,
                  cu.username AS creator_username,
                  NULL AS last_uploader_nickname,
                  NULL AS last_uploader_username,
                  NULL AS last_uploaded_at
           FROM knowledge_bases kb
           LEFT JOIN users cu ON cu.id = kb.created_by
           WHERE kb.id=%s""",
        (kb_id,),
    )
    return _serialize_kb(row)


async def update_knowledge_base(kb_id: int, name: str | None, description: str | None, owner_team: str | None) -> dict:
    row = await db.fetch_one("SELECT id FROM knowledge_bases WHERE id=%s", (kb_id,))
    if not row:
        raise HTTPException(status_code=404, detail="知识库不存在")
    if name:
        dup = await db.fetch_one("SELECT id FROM knowledge_bases WHERE name=%s AND id<>%s", (name, kb_id))
        if dup:
            raise HTTPException(status_code=409, detail="知识库名称已存在")
    await db.execute(
        """UPDATE knowledge_bases SET
           name=COALESCE(%s, name),
           description=COALESCE(%s, description),
           owner_team=COALESCE(%s, owner_team)
           WHERE id=%s""",
        (name, description, owner_team, kb_id),
    )
    updated = await db.fetch_one(
        """SELECT kb.*, COUNT(d.id) AS document_count,
                  cu.nickname AS creator_nickname,
                  cu.username AS creator_username,
                  (
                    SELECT u.nickname FROM documents ld
                    LEFT JOIN users u ON u.id = ld.created_by
                    WHERE ld.knowledge_base_id = kb.id ORDER BY ld.updated_at DESC LIMIT 1
                  ) AS last_uploader_nickname,
                  (
                    SELECT u.username FROM documents ld
                    LEFT JOIN users u ON u.id = ld.created_by
                    WHERE ld.knowledge_base_id = kb.id ORDER BY ld.updated_at DESC LIMIT 1
                  ) AS last_uploader_username,
                  (
                    SELECT MAX(ld.updated_at) FROM documents ld WHERE ld.knowledge_base_id = kb.id
                  ) AS last_uploaded_at
           FROM knowledge_bases kb
           LEFT JOIN documents d ON d.knowledge_base_id = kb.id
           LEFT JOIN users cu ON cu.id = kb.created_by
           WHERE kb.id=%s GROUP BY kb.id""",
        (kb_id,),
    )
    return _serialize_kb(updated)


async def delete_knowledge_base(kb_id: int) -> None:
    row = await db.fetch_one("SELECT id FROM knowledge_bases WHERE id=%s", (kb_id,))
    if not row:
        raise HTTPException(status_code=404, detail="知识库不存在")
    count_row = await db.fetch_one(
        "SELECT COUNT(*) AS total FROM documents WHERE knowledge_base_id=%s",
        (kb_id,),
    )
    if count_row and count_row["total"] > 0:
        raise HTTPException(status_code=409, detail="知识库下仍有文档，无法删除")
    await db.execute("DELETE FROM knowledge_bases WHERE id=%s", (kb_id,))


# ---------------- 文档 CRUD ----------------

async def list_kb_documents(
    page: int,
    page_size: int,
    knowledge_base_id: int | None = None,
    keyword: str | None = None,
) -> dict:
    where, params = ["d.knowledge_base_id IS NOT NULL"], []
    if knowledge_base_id:
        where.append("d.knowledge_base_id = %s")
        params.append(knowledge_base_id)
    if keyword:
        where.append("(d.file_name LIKE %s OR u.nickname LIKE %s OR d.doc_source LIKE %s)")
        params.extend([f"%{keyword}%", f"%{keyword}%", f"%{keyword}%"])

    where_sql = f"WHERE {' AND '.join(where)}"
    offset = (page - 1) * page_size

    total_row = await db.fetch_one(
        f"""SELECT COUNT(*) AS total FROM documents d
            LEFT JOIN users u ON u.id = d.created_by
            {where_sql}""",
        tuple(params),
    )
    rows = await db.fetch_all(
        f"""SELECT d.*, u.nickname AS uploader
            FROM documents d
            LEFT JOIN users u ON u.id = d.created_by
            {where_sql}
            ORDER BY d.updated_at DESC LIMIT %s OFFSET %s""",
        tuple(params + [page_size, offset]),
    )
    return {
        "total": total_row["total"],
        "items": [_serialize_doc(row) for row in rows],
    }


async def get_kb_document(doc_id: int) -> dict:
    row = await db.fetch_one(
        """SELECT d.*, u.nickname AS uploader
           FROM documents d
           LEFT JOIN users u ON u.id = d.created_by
           WHERE d.id=%s""",
        (doc_id,),
    )
    if not row:
        raise HTTPException(status_code=404, detail="文档不存在")
    return _serialize_doc(row)


async def upload_document(knowledge_base_id: int, file: UploadFile, user_id: int) -> tuple[dict, int]:
    kb = await db.fetch_one("SELECT id FROM knowledge_bases WHERE id=%s", (knowledge_base_id,))
    if not kb:
        raise HTTPException(status_code=404, detail="知识库不存在")

    filename = file.filename or "unnamed"
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="不支持的文件类型，请上传 PDF、Markdown、Word(.docx) 或 TXT")
    if ext == ".doc":
        raise HTTPException(status_code=400, detail="不支持 .doc，请使用 .docx 格式")

    content = await file.read()
    size_bytes = len(content)
    if size_bytes == 0:
        raise HTTPException(status_code=400, detail="文件为空")

    settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = re.sub(r"[^\w.\-]", "_", filename)
    stored_name = f"{uuid.uuid4().hex}_{safe_name}"
    storage_path = settings.UPLOAD_DIR / str(knowledge_base_id) / stored_name
    storage_path.parent.mkdir(parents=True, exist_ok=True)
    storage_path.write_bytes(content)

    mime_type = file.content_type or mimetypes.guess_type(filename)[0] or "application/octet-stream"
    doc_type = _normalize_doc_type(ext)
    doc_source = _build_upload_doc_source(knowledge_base_id, filename)
    await _replace_existing_upload(knowledge_base_id, filename, doc_type)

    try:
        doc_id = await db.execute_lastrowid(
            """INSERT INTO documents
               (knowledge_base_id, file_name, size_bytes, mime_type, storage_path, created_by,
                index_status, doc_source, doc_type, team, status)
               VALUES (%s, %s, %s, %s, %s, %s, 'processing', %s, %s, %s, 'active')""",
            (
                knowledge_base_id,
                filename,
                size_bytes,
                mime_type,
                str(storage_path),
                user_id,
                doc_source,
                doc_type,
                "default",
            ),
        )
    except IntegrityError:
        raise HTTPException(
            status_code=409,
            detail=f"文档「{filename}」已存在，请先删除旧文档或重命名后再上传",
        ) from None

    row = await db.fetch_one(
        """SELECT d.*, u.nickname AS uploader
           FROM documents d LEFT JOIN users u ON u.id = d.created_by WHERE d.id=%s""",
        (doc_id,),
    )
    return _serialize_doc(row), doc_id


async def init_oss_upload(
    knowledge_base_id: int,
    file_name: str,
    file_size: int,
    content_type: str | None,
    user_id: int,
) -> dict:
    """创建文档记录并返回 OSS 预签名直传信息。"""
    from backend.app.services import oss_service

    if not oss_service.is_enabled():
        raise HTTPException(status_code=400, detail="OSS 未启用，请使用本地上传")

    kb = await db.fetch_one("SELECT id FROM knowledge_bases WHERE id=%s", (knowledge_base_id,))
    if not kb:
        raise HTTPException(status_code=404, detail="知识库不存在")

    ext = Path(file_name).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="不支持的文件类型，请上传 PDF、Markdown、Word(.docx) 或 TXT")

    object_key = oss_service.build_object_key(knowledge_base_id, file_name)
    # 不在预签名中绑定 Content-Type，减少浏览器 CORS 预检与签名头不一致导致的直传失败
    presign = oss_service.create_presigned_put_url(object_key, None)
    oss_storage = oss_service.oss_uri(presign["bucket"], object_key)

    mime_type = content_type or mimetypes.guess_type(file_name)[0] or "application/octet-stream"
    doc_type = _normalize_doc_type(ext)
    await _replace_existing_upload(knowledge_base_id, file_name, doc_type)

    try:
        doc_id = await db.execute_lastrowid(
            """INSERT INTO documents
               (knowledge_base_id, file_name, size_bytes, mime_type, storage_path, created_by,
                index_status, doc_source, doc_type, team, status)
               VALUES (%s, %s, %s, %s, %s, %s, 'processing', %s, %s, %s, 'active')""",
            (
                knowledge_base_id,
                file_name,
                file_size,
                mime_type,
                oss_storage,
                user_id,
                object_key,
                doc_type,
                "default",
            ),
        )
    except IntegrityError:
        raise HTTPException(
            status_code=409,
            detail=f"文档「{file_name}」已存在，请先删除旧文档或重命名后再上传",
        ) from None

    row = await db.fetch_one(
        """SELECT d.*, u.nickname AS uploader
           FROM documents d LEFT JOIN users u ON u.id = d.created_by WHERE d.id=%s""",
        (doc_id,),
    )
    doc = _serialize_doc(row)
    return {
        "document": doc,
        "docId": doc_id,
        "uploadUrl": presign["url"],
        "method": presign["method"],
        "headers": presign["headers"],
        "expiresAt": presign["expiresAt"],
        "objectKey": object_key,
        "bucket": presign["bucket"],
    }


async def complete_oss_upload(doc_id: int) -> dict:
    """OSS 直传完成后：下载到本地并触发切块入库。"""
    from backend.app.services import oss_service

    row = await db.fetch_one("SELECT * FROM documents WHERE id=%s", (doc_id,))
    if not row:
        raise HTTPException(status_code=404, detail="文档不存在")

    parsed = oss_service.parse_oss_uri(row.get("storage_path") or "")
    if not parsed:
        raise HTTPException(status_code=400, detail="该文档不是 OSS 待完成上传")

    _bucket, object_key = parsed
    if not oss_service.head_object(object_key):
        raise HTTPException(status_code=400, detail="OSS 上未找到该文件，请确认上传成功")

    settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = re.sub(r"[^\w.\-]", "_", row["file_name"])
    local_path = settings.UPLOAD_DIR / str(row["knowledge_base_id"]) / f"{doc_id}_{safe_name}"
    await asyncio.to_thread(oss_service.download_to_path, object_key, local_path)

    await db.execute(
        "UPDATE documents SET storage_path=%s, size_bytes=%s WHERE id=%s",
        (str(local_path), local_path.stat().st_size, doc_id),
    )

    row = await db.fetch_one(
        """SELECT d.*, u.nickname AS uploader
           FROM documents d LEFT JOIN users u ON u.id = d.created_by WHERE d.id=%s""",
        (doc_id,),
    )
    return _serialize_doc(row)


def resolve_ingest_local_path(storage_path: str) -> Path:
    from backend.app.services import oss_service

    parsed = oss_service.parse_oss_uri(storage_path)
    if parsed:
        _bucket, object_key = parsed
        cache_path = settings.UPLOAD_DIR / "oss-cache" / object_key.replace("/", "_")
        if not cache_path.exists():
            oss_service.download_to_path(object_key, cache_path)
        return cache_path
    path = Path(storage_path)
    if not path.exists():
        raise FileNotFoundError(f"文件不存在: {storage_path}")
    return path


async def ingest_document_by_id(doc_id: int) -> None:
    """后台任务：加载文档 → 父子切块 → 向量化写入 Milvus。"""
    try:
        await asyncio.to_thread(run_ingest_for_document, doc_id)
        logger.info("文档入库完成 doc_id=%s", doc_id)
    except Exception as exc:
        logger.exception("文档入库失败 doc_id=%s: %s", doc_id, exc)
        await db.execute("UPDATE documents SET index_status='failed' WHERE id=%s", (doc_id,))


def run_ingest_for_document(doc_id: int) -> dict:
    from internal_kb_qa.scripts.ingest_documents import ingest_upload_file

    row = db_sync_fetch_document(doc_id)
    if not row:
        raise ValueError(f"文档不存在: {doc_id}")
    storage_path = row.get("storage_path")
    if not storage_path:
        raise ValueError("文档缺少 storage_path")

    path = resolve_ingest_local_path(storage_path)

    kb_row = db_sync_fetch_knowledge_base(row.get("knowledge_base_id"))
    kb_name = kb_row.get("name") if kb_row else None
    kb_team = kb_row.get("owner_team") if kb_row else None

    return ingest_upload_file(
        path,
        knowledge_base_id=row.get("knowledge_base_id"),
        doc_id=doc_id,
        kb_name=kb_name,
        kb_team=kb_team,
        file_display_name=row.get("file_name"),
        delete_existing=True,
    )


def _run_ingest_for_document(doc_id: int) -> dict:
    return run_ingest_for_document(doc_id)


def db_sync_fetch_knowledge_base(kb_id: int | None) -> dict | None:
    if not kb_id:
        return None
    import pymysql
    from base.config import Config

    conf = Config()
    conn = pymysql.connect(
        host=conf.MYSQL_HOST,
        user=conf.MYSQL_USER,
        password=conf.MYSQL_PASSWORD,
        database=conf.MYSQL_DATABASE,
        charset="utf8mb4",
    )
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute(
                "SELECT id, name, owner_team FROM knowledge_bases WHERE id=%s",
                (kb_id,),
            )
            return cursor.fetchone()
    finally:
        conn.close()


def db_sync_fetch_document(doc_id: int) -> dict | None:
    """同步读取文档行（后台 ingest 线程使用）。"""
    import pymysql
    from base.config import Config

    conf = Config()
    conn = pymysql.connect(
        host=conf.MYSQL_HOST,
        user=conf.MYSQL_USER,
        password=conf.MYSQL_PASSWORD,
        database=conf.MYSQL_DATABASE,
        charset="utf8mb4",
    )
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute(
                "SELECT id, knowledge_base_id, storage_path, file_name FROM documents WHERE id=%s",
                (doc_id,),
            )
            return cursor.fetchone()
    finally:
        conn.close()


async def _mark_document_indexed(doc_id: int) -> None:
    """兼容旧调用：触发真实 ingest。"""
    await ingest_document_by_id(doc_id)


async def update_document(doc_id: int, file_name: str) -> dict:
    row = await db.fetch_one("SELECT id FROM documents WHERE id=%s", (doc_id,))
    if not row:
        raise HTTPException(status_code=404, detail="文档不存在")
    await db.execute(
        "UPDATE documents SET file_name=%s WHERE id=%s",
        (file_name, doc_id),
    )
    return await get_kb_document(doc_id)


async def delete_document(doc_id: int) -> None:
    from backend.app.services import oss_service

    row = await db.fetch_one("SELECT id, storage_path, doc_source FROM documents WHERE id=%s", (doc_id,))
    if not row:
        raise HTTPException(status_code=404, detail="文档不存在")
    storage_path = row.get("storage_path") or ""
    parsed = oss_service.parse_oss_uri(storage_path)
    if parsed:
        _bucket, object_key = parsed
        await asyncio.to_thread(oss_service.delete_object, object_key)
    if storage_path and not storage_path.startswith("oss://"):
        path = Path(storage_path)
        if path.exists():
            try:
                path.unlink(missing_ok=True)
            except OSError as exc:
                logger.warning("删除本地文件失败 path=%s: %s", path, exc)
        await asyncio.to_thread(_delete_milvus_for_path, storage_path)
    elif storage_path:
        await asyncio.to_thread(_delete_milvus_for_path, storage_path)
    await db.execute("DELETE FROM documents WHERE id=%s", (doc_id,))


def _delete_milvus_for_path(storage_path: str) -> None:
    from pymilvus import MilvusClient

    from base.config import Config
    from internal_kb_qa.core.milvus_paths import build_file_path_filter

    conf = Config()
    client = MilvusClient(uri=f"http://{conf.MILVUS_HOST}:{conf.MILVUS_PORT}", db_name=conf.MILVUS_DATABASE_NAME)
    if not client.has_collection(conf.MILVUS_COLLECTION_NAME):
        return
    expr = build_file_path_filter([storage_path])
    if not expr:
        return
    try:
        client.delete(collection_name=conf.MILVUS_COLLECTION_NAME, filter=expr)
        client.flush(conf.MILVUS_COLLECTION_NAME)
        logger.info("Milvus 已删除文档向量 path=%s", storage_path)
    except Exception as exc:
        logger.warning("Milvus 删除失败 path=%s: %s", storage_path, exc)


# ---------------- 旧版文档列表（兼容） ----------------

async def list_documents(page: int, page_size: int, keyword: str | None = None, doc_type: str | None = None, team: str | None = None) -> dict:
    where, params = [], []
    if keyword:
        where.append("(doc_source LIKE %s OR doc_type LIKE %s OR file_name LIKE %s)")
        params.extend([f"%{keyword}%", f"%{keyword}%", f"%{keyword}%"])
    if doc_type:
        where.append("doc_type = %s")
        params.append(doc_type)
    if team:
        where.append("team = %s")
        params.append(team)

    where_sql = f"WHERE {' AND '.join(where)}" if where else ""
    offset = (page - 1) * page_size

    total_row = await db.fetch_one(f"SELECT COUNT(*) AS total FROM documents {where_sql}", tuple(params))
    rows = await db.fetch_all(
        f"""SELECT id, doc_source, doc_type, team, system_name, version, security_level, status, chunk_count, last_updated,
                   file_name, size_bytes, index_status, knowledge_base_id, updated_at
            FROM documents {where_sql} ORDER BY updated_at DESC LIMIT %s OFFSET %s""",
        tuple(params + [page_size, offset]),
    )
    return {"total": total_row["total"], "items": rows}


async def get_document(doc_id: int) -> dict:
    row = await db.fetch_one(
        """SELECT id, doc_source, doc_type, team, system_name, version, security_level, status, chunk_count, last_updated,
                  file_name, size_bytes, index_status, knowledge_base_id, updated_at
           FROM documents WHERE id=%s""",
        (doc_id,),
    )
    if not row:
        raise HTTPException(status_code=404, detail="文档不存在")
    return row


# ---------------- 高频 FAQ ----------------

async def list_faq(page: int, page_size: int, keyword: str | None = None, category: str | None = None, team: str | None = None) -> dict:
    where, params = [], []
    if keyword:
        where.append("(question LIKE %s OR keywords LIKE %s OR answer LIKE %s)")
        params.extend([f"%{keyword}%", f"%{keyword}%", f"%{keyword}%"])
    if category:
        where.append("category = %s")
        params.append(category)
    if team:
        where.append("team = %s")
        params.append(team)

    where.append("is_active = 1")
    where_sql = f"WHERE {' AND '.join(where)}"
    offset = (page - 1) * page_size

    total_row = await db.fetch_one(f"SELECT COUNT(*) AS total FROM faq {where_sql}", tuple(params))
    rows = await db.fetch_all(
        f"""SELECT id, question, answer, doc_source, category, team, system_name, security_level, version, last_updated
            FROM faq {where_sql} ORDER BY updated_at DESC LIMIT %s OFFSET %s""",
        tuple(params + [page_size, offset]),
    )
    return {"total": total_row["total"], "items": rows}


async def get_faq(faq_id: int) -> dict:
    row = await db.fetch_one(
        """SELECT id, question, answer, doc_source, category, team, system_name, security_level, version, last_updated
           FROM faq WHERE id=%s AND is_active=1""",
        (faq_id,),
    )
    if not row:
        raise HTTPException(status_code=404, detail="FAQ 不存在")
    return row


async def search_faq_question(question: str) -> dict:
    """用户问题查询：Redis 缓存 -> MySQL -> 空值缓存。"""
    question = question.strip()
    if not question:
        return {"found": False, "cached": False, "message": "问题不能为空"}

    # 1. 先查 Redis 缓存
    exists, cached_data = await cache.get_question_cache(question)
    if exists:
        if cached_data is None:
            return {"found": False, "cached": True}
        cached_data["cached"] = True
        return cached_data

    # 2. 尝试获取重建锁，避免热点问题同时打 MySQL
    lock_ok = await cache.acquire_question_lock(question)
    if not lock_ok:
        # 3. 拿不到锁就指数退避等待其他请求写入缓存
        exists, cached_data = await cache.wait_and_get_cache(question)
        if exists:
            if cached_data is None:
                return {"found": False, "cached": True}
            cached_data["cached"] = True
            return cached_data
        # 退避后仍未命中，直接查库兜底（不让请求无限等待）
        return await _query_and_cache(question, cached=False)

    try:
        # 4. 拿到锁后二次检查缓存，避免重复查库
        exists, cached_data = await cache.get_question_cache(question)
        if exists:
            if cached_data is None:
                return {"found": False, "cached": True}
            cached_data["cached"] = True
            return cached_data
        return await _query_and_cache(question, cached=False)
    finally:
        await cache.release_question_lock(question)


async def _query_and_cache(question: str, cached: bool = False) -> dict:
    """查询 MySQL，并把结果写回 Redis。"""
    # 先精确匹配，再尝试 LIKE 模糊匹配
    row = await db.fetch_one(
        "SELECT * FROM faq WHERE question=%s AND is_active=1 LIMIT 1",
        (question,),
    )
    if not row:
        row = await db.fetch_one(
            """SELECT * FROM faq
               WHERE question LIKE %s AND is_active=1
               ORDER BY CHAR_LENGTH(question) ASC LIMIT 1""",
            (f"%{question}%",),
        )

    if not row:
        # 缓存穿透保护：查不到也写空缓存
        await cache.set_question_empty(question)
        return {"found": False, "cached": cached}

    result = {
        "found": True,
        "cached": cached,
        "question": row["question"],
        "answer": row["answer"],
        "source": row.get("doc_source"),
        "category": row.get("category"),
        "team": row.get("team"),
        "security_level": row.get("security_level"),
    }
    await cache.set_question_cache(question, result)
    result["cached"] = False
    return result


def _normalize_path(value: str) -> str:
    return str(Path(value).resolve()).replace("\\", "/").lower()


def _doc_type_label(name: str, doc_type: str | None = None) -> str:
    if doc_type in {"wiki", "runbook", "faq", "report"}:
        return doc_type.upper()
    ext = Path(name).suffix.lower()
    mapping = {".pdf": "PDF", ".md": "MD", ".doc": "DOC", ".docx": "DOC", ".txt": "TXT"}
    return mapping.get(ext, "FILE")


def _rewrite_for_retrieval(question: str, *, use_llm: bool = False) -> tuple[str, list[str]]:
    """检索用 Query 改写：默认规则改写，避免聊天场景额外调用 LLM。"""
    from base.config import Config
    from internal_kb_qa.core.intent_classifier import CATEGORY_TECH
    from internal_kb_qa.core.query_rewrite import _apply_colloquial_rules

    conf = Config()
    if use_llm and conf.DASHSCOPE_API_KEY:
        try:
            from internal_kb_qa.core.query_rewrite import query_rewrite

            rewritten = query_rewrite(question, None, CATEGORY_TECH)
            queries = rewritten.search_queries or [rewritten.rewritten_query or question]
            return rewritten.rewritten_query or question, queries
        except Exception as exc:
            logger.warning("LLM Query 改写失败，回退规则改写: %s", exc)

    rewritten = _apply_colloquial_rules(question)
    return rewritten, [rewritten]


def _run_hybrid_search(
    question: str,
    top_k: int,
    mode: str,
    use_rerank: bool,
    file_paths: list[str] | None = None,
):
    from internal_kb_qa.core.hybrid_search import search

    filter_payload = {"file_paths": file_paths} if file_paths else None
    return search(question, top_k=top_k, filter=filter_payload, mode=mode, use_rerank=use_rerank)


def _extract_worker_json(stdout: bytes) -> dict | None:
    text = (stdout or b"").decode("utf-8", errors="replace")
    for line in reversed(text.splitlines()):
        line = line.strip()
        if line.startswith("{"):
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue
    return None


def _run_hybrid_search_isolated(
    queries: list[str],
    top_k: int,
    mode: str,
    use_rerank: bool,
    file_paths: list[str] | None = None,
) -> tuple[list, str | None]:
    import json
    import subprocess
    import sys

    from backend.app.core.config import PROJECT_ROOT
    from internal_kb_qa.core.hit import Hit

    if not queries:
        return [], None

    payload = {
        "queries": queries,
        "top_k": top_k,
        "mode": mode,
        "use_rerank": use_rerank,
        "file_paths": file_paths,
    }
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "internal_kb_qa.scripts.retrieval_worker"],
            input=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            capture_output=True,
            timeout=180,
            cwd=str(PROJECT_ROOT),
        )
    except subprocess.TimeoutExpired:
        logger.warning("检索 worker 超时 queries=%s", queries[0][:80])
        return [], "检索超时，请关闭精排后重试"

    if proc.stderr:
        stderr_text = proc.stderr.decode("utf-8", errors="replace").strip()
        if stderr_text:
            logger.debug("检索 worker stderr: %s", stderr_text[-500:])

    result = _extract_worker_json(proc.stdout)
    if result is None:
        logger.warning(
            "检索 worker 输出无法解析 code=%s stdout=%s",
            proc.returncode,
            (proc.stdout or b"").decode("utf-8", errors="replace")[-300:],
        )
        return [], "检索进程输出异常"

    if not result.get("ok"):
        error = result.get("error") or "检索失败"
        logger.warning("检索 worker 失败: %s", error)
        return [], str(error)

    hits = [Hit(text=text, score=score, metadata=meta) for text, score, meta in result["hits"]]
    return hits, None


def _merge_retrieval_hits(hits_list: list) -> list:
    """多路 Query 召回合并，按 parent_id 保留最高分。"""
    best: dict[str, object] = {}
    for hit in hits_list:
        meta = hit.metadata or {}
        key = meta.get("parent_id") or meta.get("child_id") or hit.text[:80]
        if key not in best or hit.score > best[key].score:
            best[key] = hit
    return sorted(best.values(), key=lambda h: h.score, reverse=True)


async def search_retrieval(
    question: str,
    knowledge_base_id: int | None = None,
    top_k: int = 5,
    mode: str = "hybrid",
    use_rerank: bool = False,
    use_llm_rewrite: bool = False,
) -> dict:
    """Milvus 混合检索，返回前端检索测试页所需结构。"""
    question = question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="问题不能为空")

    allowed_paths: list[str] = []
    doc_index: dict[str, dict] = {}
    kb_name = None

    if knowledge_base_id:
        kb = await db.fetch_one("SELECT id, name FROM knowledge_bases WHERE id=%s", (knowledge_base_id,))
        if not kb:
            raise HTTPException(status_code=404, detail="知识库不存在")
        kb_name = kb["name"]
        rows = await db.fetch_all(
            """SELECT file_name, storage_path, doc_source, doc_type
               FROM documents WHERE knowledge_base_id=%s AND status='active'""",
            (knowledge_base_id,),
        )
        if not rows:
            return {
                "question": question,
                "rewrittenQuery": question,
                "searchQueries": [question],
                "knowledgeBase": kb_name,
                "total": 0,
                "items": [],
                "mode": mode,
                "modeLabel": {"hybrid": "混合检索", "dense": "稠密向量", "sparse": "稀疏向量"}.get(mode, mode),
                "reranker": "bge-reranker-v2-m3" if use_rerank else "none",
                "useRerank": use_rerank,
                "topK": top_k,
            }
        for row in rows:
            doc_index[row["file_name"].lower()] = row
            storage = row.get("storage_path")
            if not storage or str(storage).startswith("oss://"):
                continue
            from internal_kb_qa.core.milvus_paths import candidate_paths

            for path in candidate_paths(storage):
                allowed_paths.append(path)
        allowed_paths = list(dict.fromkeys(allowed_paths))

    rewritten, search_queries = await asyncio.to_thread(_rewrite_for_retrieval, question, use_llm=use_llm_rewrite)

    retrieval_warning = None
    try:
        hits, worker_error = await asyncio.to_thread(
            _run_hybrid_search_isolated,
            search_queries[:1 if not use_llm_rewrite else 2],
            top_k,
            mode,
            use_rerank,
            allowed_paths if knowledge_base_id else None,
        )
        if worker_error:
            retrieval_warning = worker_error
        hits = _merge_retrieval_hits(hits)
    except Exception as exc:
        logger.exception("向量检索失败 question=%s: %s", question[:80], exc)
        hits = []
        retrieval_warning = f"向量检索异常：{exc}"

    items = []
    for hit in hits:
        meta = hit.metadata or {}
        file_path = meta.get("file_path") or ""
        file_name = Path(file_path).name if file_path else ""

        doc_row = doc_index.get(file_name.lower(), {}) if file_name else {}
        display_name = doc_row.get("file_name") or file_name or meta.get("title") or f"知识片段（{meta.get('source', 'unknown')}）"
        parent_id = meta.get("parent_id") or ""
        child_id = meta.get("child_id") or ""
        child_text = (meta.get("matched_child_text") or "").strip()
        snippet = child_text or (hit.text or "").strip()
        if len(snippet) > 280:
            snippet = snippet[:280] + "…"

        items.append(
            {
                "score": f"{hit.score:.2f}",
                "doc": display_name,
                "type": _doc_type_label(display_name, doc_row.get("doc_type")),
                "location": f"Chunk · {(child_id or parent_id)[-12:]}" if (child_id or parent_id) else "向量片段",
                "snippet": snippet,
                "chunkId": child_id or parent_id or meta.get("source", "chunk"),
                "parentId": parent_id,
                "source": meta.get("source"),
            }
        )
        if len(items) >= top_k:
            break

    mode_labels = {"hybrid": "混合检索", "dense": "稠密向量", "sparse": "稀疏向量"}
    return {
        "question": question,
        "rewrittenQuery": rewritten,
        "searchQueries": search_queries,
        "knowledgeBase": kb_name,
        "total": len(items),
        "items": items,
        "mode": mode,
        "modeLabel": mode_labels.get(mode, mode),
        "reranker": "bge-reranker-v2-m3" if use_rerank else "none",
        "useRerank": use_rerank,
        "topK": top_k,
        "warning": retrieval_warning,
    }


def _run_chunk_query(storage_path: str) -> tuple[list[dict], list[dict]]:
    from internal_kb_qa.core.chunk_query import group_chunks, query_chunks_by_file_path

    rows = query_chunks_by_file_path(storage_path)
    return rows, group_chunks(rows)


async def list_document_chunks(doc_id: int) -> dict:
    """查询指定文档在 Milvus 中的全部切块。"""
    row = await db.fetch_one(
        """SELECT d.*, kb.name AS kb_name, u.nickname AS uploader
           FROM documents d
           LEFT JOIN knowledge_bases kb ON kb.id = d.knowledge_base_id
           LEFT JOIN users u ON u.id = d.created_by
           WHERE d.id=%s""",
        (doc_id,),
    )
    if not row:
        raise HTTPException(status_code=404, detail="文档不存在")

    storage_path = row.get("storage_path") or row.get("doc_source")
    if not storage_path:
        raise HTTPException(status_code=400, detail="文档缺少存储路径，无法查询切块")

    milvus_rows, parents = await asyncio.to_thread(_run_chunk_query, storage_path)
    doc = _serialize_doc(row)
    doc["kbName"] = row.get("kb_name")

    return {
        "document": doc,
        "milvusCount": len(milvus_rows),
        "mysqlChunkCount": row.get("chunk_count") or 0,
        "parentCount": len(parents),
        "parents": parents,
        "storagePath": storage_path,
    }
