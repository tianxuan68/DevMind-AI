"""T12 客户端后端响应模型。"""
from pydantic import BaseModel


class BootstrapResponse(BaseModel):
    announcements: list = []
    help_links: list = []
    features: dict = {}
