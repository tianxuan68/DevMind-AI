"""API 请求/响应模型。"""
from pydantic import BaseModel, Field


# ---------------- 用户认证 ----------------

class SendCodeRequest(BaseModel):
    phone: str = Field(min_length=6, max_length=20, description="手机号")


class RegisterRequest(BaseModel):
    username: str = Field(min_length=2, max_length=64, description="登录账号")
    password: str = Field(min_length=6, max_length=64, description="密码")
    nickname: str | None = Field(default=None, max_length=100)
    phone: str = Field(min_length=6, max_length=20)
    sms_code: str = Field(min_length=4, max_length=8)
    team: str = "default"


class LoginRequest(BaseModel):
    account: str = Field(min_length=2, max_length=64, description="用户名或手机号")
    password: str = Field(min_length=1, max_length=64)


class SmsLoginRequest(BaseModel):
    phone: str = Field(min_length=6, max_length=20)
    sms_code: str = Field(min_length=4, max_length=8)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict


# ---------------- 知识库 ----------------

class DocumentQuery(BaseModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=10, ge=1, le=100)
    keyword: str | None = None
    doc_type: str | None = None
    team: str | None = None


class FAQQuery(BaseModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=10, ge=1, le=100)
    keyword: str | None = None
    category: str | None = None
    team: str | None = None


class FAQSearchRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)


class KnowledgeBaseCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=500)
    owner_team: str | None = Field(default=None, max_length=100)


class KnowledgeBaseUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=500)
    owner_team: str | None = Field(default=None, max_length=100)


class DocumentUpdate(BaseModel):
    file_name: str = Field(min_length=1, max_length=500)
