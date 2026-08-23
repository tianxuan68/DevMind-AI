"""知识库接口：知识库与文档 CRUD、上传。"""
from fastapi import APIRouter, Depends, File, Form, Query, UploadFile

from backend.app.core.security import get_current_user
from backend.app.schemas import DocumentUpdate, KnowledgeBaseCreate, KnowledgeBaseUpdate
from backend.app.services import knowledge_service as svc

router = APIRouter(prefix="/api/knowledge", tags=["知识库"])


@router.get("/bases")
async def list_bases(_: dict = Depends(get_current_user)):
    """知识库列表。"""
    return {"items": await svc.list_knowledge_bases()}


@router.post("/bases")
async def create_base(body: KnowledgeBaseCreate, current_user: dict = Depends(get_current_user)):
    """新建知识库。"""
    return await svc.create_knowledge_base(
        body.name, body.description, body.owner_team, current_user["id"]
    )


@router.patch("/bases/{kb_id}")
async def update_base(kb_id: int, body: KnowledgeBaseUpdate, _: dict = Depends(get_current_user)):
    """编辑知识库。"""
    return await svc.update_knowledge_base(kb_id, body.name, body.description, body.owner_team)


@router.delete("/bases/{kb_id}")
async def delete_base(kb_id: int, _: dict = Depends(get_current_user)):
    """删除空知识库。"""
    await svc.delete_knowledge_base(kb_id)
    return {"message": "删除成功"}


@router.get("/docs")
async def docs(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    knowledge_base_id: int | None = None,
    keyword: str | None = None,
    _: dict = Depends(get_current_user),
):
    """分页查看知识库文档（工作台）。"""
    return await svc.list_kb_documents(page, page_size, knowledge_base_id, keyword)


@router.post("/docs")
async def upload_doc(
    knowledge_base_id: int = Form(...),
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
):
    """上传文档。"""
    return await svc.upload_document(knowledge_base_id, file, current_user["id"])


@router.get("/docs/{doc_id}")
async def doc_detail(doc_id: int, _: dict = Depends(get_current_user)):
    """查看单个文档详情。"""
    return await svc.get_kb_document(doc_id)


@router.patch("/docs/{doc_id}")
async def update_doc(doc_id: int, body: DocumentUpdate, _: dict = Depends(get_current_user)):
    """重命名文档。"""
    return await svc.update_document(doc_id, body.file_name)


@router.delete("/docs/{doc_id}")
async def delete_doc(doc_id: int, _: dict = Depends(get_current_user)):
    """删除文档。"""
    await svc.delete_document(doc_id)
    return {"message": "删除成功"}
