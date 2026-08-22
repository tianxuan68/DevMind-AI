"""知识库接口：查看知识库文档列表/详情。"""
from fastapi import APIRouter, Query

from backend.app.services.knowledge_service import get_document, list_documents

router = APIRouter(prefix="/api/knowledge", tags=["知识库"])


@router.get("/docs")
async def docs(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    keyword: str | None = None,
    doc_type: str | None = None,
    team: str | None = None,
):
    """分页查看知识库文档。"""
    return await list_documents(page, page_size, keyword, doc_type, team)


@router.get("/docs/{doc_id}")
async def doc_detail(doc_id: int):
    """查看单个文档详情。"""
    return await get_document(doc_id)
