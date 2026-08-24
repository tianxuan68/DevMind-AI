"""知识库接口：知识库与文档 CRUD、上传。"""
from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, Query, UploadFile

from backend.app.core.security import get_current_user
from backend.app.schemas import (
    DocumentUpdate,
    KnowledgeBaseCreate,
    KnowledgeBaseUpdate,
    OssUploadInitRequest,
    RetrievalSearchRequest,
)
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
    background_tasks: BackgroundTasks,
    knowledge_base_id: int = Form(...),
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
):
    """本地上传（OSS 未启用时的回退方案）。"""
    doc, doc_id = await svc.upload_document(knowledge_base_id, file, current_user["id"])
    background_tasks.add_task(svc.ingest_document_by_id, doc_id)
    return doc


@router.post("/docs/oss/init")
async def oss_upload_init(body: OssUploadInitRequest, current_user: dict = Depends(get_current_user)):
    """初始化 OSS 直传：返回预签名 URL，浏览器可上报真实上传进度。"""
    return await svc.init_oss_upload(
        body.knowledge_base_id,
        body.file_name,
        body.file_size,
        body.content_type,
        current_user["id"],
    )


@router.post("/docs/{doc_id}/oss/complete")
async def oss_upload_complete(
    doc_id: int,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
):
    """OSS 直传完成后确认，并后台切块入库。"""
    doc = await svc.complete_oss_upload(doc_id)
    background_tasks.add_task(svc.ingest_document_by_id, doc_id)
    return doc


@router.get("/docs/{doc_id}/chunks")
async def doc_chunks(doc_id: int, _: dict = Depends(get_current_user)):
    """查看文档在 Milvus 中的切块列表。"""
    return await svc.list_document_chunks(doc_id)


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


@router.post("/retrieval/search")
async def retrieval_search(body: RetrievalSearchRequest, _: dict = Depends(get_current_user)):
    """检索测试：Milvus 混合检索 + 重排（不调用大模型）。"""
    return await svc.search_retrieval(
        body.question,
        body.knowledge_base_id,
        body.top_k,
        body.mode,
        body.use_rerank,
        body.use_llm_rewrite,
    )
