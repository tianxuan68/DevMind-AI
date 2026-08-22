"""知识库与 FAQ 服务。

FAQ 搜索走 Redis 问题缓存：
- 有缓存直接返回，不打 MySQL
- 没有缓存且 MySQL 查到，写入随机 TTL 缓存
- MySQL 也查不到，写空值短缓存，防止缓存穿透打爆 MySQL
- 并发热点问题使用 Redis 锁 + 指数退避，防止缓存击穿
"""
from fastapi import HTTPException

from backend.app.core import cache
from backend.app.core.db import db

# ---------------- 文档知识库 ----------------

async def list_documents(page: int, page_size: int, keyword: str | None = None, doc_type: str | None = None, team: str | None = None) -> dict:
    where, params = [], []
    if keyword:
        where.append("(doc_source LIKE %s OR doc_type LIKE %s)")
        params.extend([f"%{keyword}%", f"%{keyword}%"])
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
        f"""SELECT id, doc_source, doc_type, team, system_name, version, security_level, status, chunk_count, last_updated
            FROM documents {where_sql} ORDER BY updated_at DESC LIMIT %s OFFSET %s""",
        tuple(params + [page_size, offset]),
    )
    return {"total": total_row["total"], "items": rows}


async def get_document(doc_id: int) -> dict:
    row = await db.fetch_one(
        """SELECT id, doc_source, doc_type, team, system_name, version, security_level, status, chunk_count, last_updated
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
