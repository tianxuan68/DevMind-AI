"""高频 FAQ 接口：列表、详情、用户问题缓存查询。"""
from fastapi import APIRouter, Depends, Query

from backend.app.core.security import get_current_user
from backend.app.schemas import FAQSearchRequest
from backend.app.services.knowledge_service import get_faq, list_faq, search_faq_question

router = APIRouter(prefix="/api/faq", tags=["高频问答"])


@router.get("")
async def faq_list(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    keyword: str | None = None,
    category: str | None = None,
    team: str | None = None,
):
    """分页查看高频问答对。"""
    return await list_faq(page, page_size, keyword, category, team)


@router.get("/{faq_id}")
async def faq_detail(faq_id: int):
    """查看单个 FAQ 详情。"""
    return await get_faq(faq_id)


@router.post("/search")
async def faq_search(req: FAQSearchRequest, current_user: dict = Depends(get_current_user)):
    """用户问题查询。

    流程：
    1. Redis 单独 db 2 缓存用户问题
    2. 缓存命中直接返回
    3. 缓存未命中查 MySQL，查不到写空缓存，防止穿透
    4. 热点问题用 Redis 锁 + 指数退避，防止缓存击穿
    """
    return await search_faq_question(req.question)
