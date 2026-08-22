"""认证接口：验证码、注册、登录、退出。"""
from fastapi import APIRouter, Depends

from backend.app.core.security import blacklist_token, create_access_token, get_current_user
from backend.app.schemas import LoginRequest, RegisterRequest, SendCodeRequest, SmsLoginRequest, TokenResponse
from backend.app.services import user_service

router = APIRouter(prefix="/api/auth", tags=["认证"])


@router.post("/send-code")
async def send_code(req: SendCodeRequest):
    """发送手机验证码。开发环境返回 debug_code 方便联调。"""
    return await user_service.send_sms_code(req.phone)


@router.post("/register")
async def register(req: RegisterRequest):
    """注册账号：用户名 + 密码 + 手机验证码。"""
    user = await user_service.register_user(
        username=req.username,
        password=req.password,
        phone=req.phone,
        sms_code=req.sms_code,
        nickname=req.nickname,
        team=req.team,
    )
    return TokenResponse(access_token=create_access_token(user), user=user)


@router.post("/login")
async def login(req: LoginRequest):
    """账号密码登录，account 支持用户名或手机号。"""
    user = await user_service.login_by_account(req.account, req.password)
    return TokenResponse(access_token=create_access_token(user), user=user)


@router.post("/login/sms")
async def login_by_sms(req: SmsLoginRequest):
    """手机号 + 验证码登录。"""
    user = await user_service.login_by_sms(req.phone, req.sms_code)
    return TokenResponse(access_token=create_access_token(user), user=user)


@router.post("/logout")
async def logout(current_user: dict = Depends(get_current_user)):
    """退出登录：将当前 JWT 的 jti 加入 Redis 黑名单。"""
    await blacklist_token(current_user)
    return {"message": "退出成功"}
