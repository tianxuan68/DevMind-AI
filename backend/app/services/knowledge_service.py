"""知识库与 FAQ 服务。"""
import asyncio
import mimetypes
import re
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import HTTPException, UploadFile

from backend.app.core import cache
from backend.app.core.config import settings
from backend.app.core.db import db

ALLOWED_EXTENSIONS = {".pdf", ".md", ".doc", ".docx", ".txt"}
STATUS_LABEL = {"processing": "处理中", "indexed": "已索引", "failed": "失败", "active": "正常"}


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


def _serialize_kb(row: dict) -> dict:
    return {
        "id": str(row["id"]),
        "name": row["name"],
        "description": row.get("description") or "",
        "owner": row.get("owner_team") or "未分配",
        "docCount": row.get("document_count") or 0,
        "status": STATUS_LABEL.get(row.get("status"), row.get("status")),
        "updatedAt": _format_dt(row.get("updated_at")),
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
        "uploader": row.get("uploader") or "—",
        "updatedAt": _format_dt(row.get("updated_at")),
    }


# ---------------- 知识库 CRUD ----------------

async def list_knowledge_bases() -> list[dict]:
    rows = await db.fetch_all(
        """SELECT kb.*, COUNT(d.id) AS document_count
           FROM knowledge_bases kb
           LEFT JOIN documents d ON d.knowledge_base_id = kb.id
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
        """SELECT kb.*, 0 AS document_count FROM knowledge_bases kb WHERE kb.id=%s""",
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
        """SELECT kb.*, COUNT(d.id) AS document_count
           FROM knowledge_bases kb
           LEFT JOIN documents d ON d.knowledge_base_id = kb.id
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


async def upload_document(knowledge_base_id: int, file: UploadFile, user_id: int) -> dict:
    kb = await db.fetch_one("SELECT id FROM knowledge_bases WHERE id=%s", (knowledge_base_id,))
    if not kb:
        raise HTTPException(status_code=404, detail="知识库不存在")

    filename = file.filename or "unnamed"
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="不支持的文件类型")

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
    doc_type = ext.lstrip(".").lower()
    if doc_type == "docx":
        doc_type = "doc"

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
            filename,
            doc_type,
            "default",
        ),
    )

    asyncio.create_task(_mark_document_indexed(doc_id))

    row = await db.fetch_one(
        """SELECT d.*, u.nickname AS uploader
           FROM documents d LEFT JOIN users u ON u.id = d.created_by WHERE d.id=%s""",
        (doc_id,),
    )
    return _serialize_doc(row)


async def _mark_document_indexed(doc_id: int) -> None:
    await asyncio.sleep(1.2)
    await db.execute("UPDATE documents SET index_status='indexed' WHERE id=%s", (doc_id,))


async def update_document(doc_id: int, file_name: str) -> dict:
    row = await db.fetch_one("SELECT id FROM documents WHERE id=%s", (doc_id,))
    if not row:
        raise HTTPException(status_code=404, detail="文档不存在")
    await db.execute(
        "UPDATE documents SET file_name=%s, doc_source=%s WHERE id=%s",
        (file_name, file_name, doc_id),
    )
    return await get_kb_document(doc_id)


async def delete_document(doc_id: int) -> None:
    row = await db.fetch_one("SELECT id, storage_path FROM documents WHERE id=%s", (doc_id,))
    if not row:
        raise HTTPException(status_code=404, detail="文档不存在")
    if row.get("storage_path"):
        path = Path(row["storage_path"])
        if path.exists():
            path.unlink(missing_ok=True)
    await db.execute("DELETE FROM documents WHERE id=%s", (doc_id,))


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
