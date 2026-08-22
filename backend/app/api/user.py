"""用户信息接口。"""
from fastapi import APIRouter, Depends

from backend.app.core.security import get_current_user

router = APIRouter(prefix="/api/user", tags=["用户"])


@router.get("/me")
async def me(current_user: dict = Depends(get_current_user)):
    """获取当前登录用户信息。"""
    return {
        "id": current_user["id"],
        "username": current_user["username"],
        "nickname": current_user["nickname"],
        "phone": current_user["phone"],
        "team": current_user["team"],
        "security_level": current_user["security_level"],
    }
