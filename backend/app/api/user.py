"""用户信息接口。"""
from fastapi import APIRouter, Depends

from backend.app.core.db import db
from backend.app.core.security import get_current_user

router = APIRouter(prefix="/api/user", tags=["用户"])


@router.get("/me")
async def me(current_user: dict = Depends(get_current_user)):
    """获取当前登录用户信息。"""
    row = await db.fetch_one(
        "SELECT id, username, nickname, phone, team, security_level, created_at, updated_at FROM users WHERE id=%s",
        (current_user["id"],),
    )
    if not row:
        return current_user
    return {
        "id": row["id"],
        "username": row["username"],
        "nickname": row["nickname"],
        "phone": row["phone"],
        "team": row["team"],
        "security_level": row["security_level"],
        "created_at": row["created_at"].isoformat(sep=" ", timespec="seconds") if row.get("created_at") else None,
        "updated_at": row["updated_at"].isoformat(sep=" ", timespec="seconds") if row.get("updated_at") else None,
    }
