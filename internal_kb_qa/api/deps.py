"""T8 SSO 身份解析与权限注入。

请求头携带 SSO token（Authorization: Bearer <token>），解析出用户身份
（user_id / name / team / security_level），并生成检索必须强制注入的
权限过滤条件（不可绕过，R9 验收硬指标：越权检索命中数为 0）。

支持两种模式（config.ini [security].sso_mode）：
- mock：token 格式 ``user_id:name:team:security_level``，用于开发联调；
  security_level 省略时取默认值（default_security_level）。
- jwt：HS256 签名 JWT（标准库实现，无需额外依赖），claims 含
  sub / name / team / security_level。

真实企业 SSO 服务接入时，替换 SSOAuth 实现（新增模式）即可，依赖方不变。
"""
import base64
import hashlib
import hmac
import json
from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException

from base.config import Config

# security_level 等级映射：数值越小越公开
SECURITY_LEVELS = {"public": 0, "team": 1, "secret": 2}
SECURITY_LEVEL_NAMES = ("public", "team", "secret")


@dataclass(frozen=True)
class UserContext:
    """SSO 解析出的用户身份。"""

    user_id: str
    name: str
    team: str
    security_level: str = "team"

    def security_rank(self) -> int:
        return SECURITY_LEVELS.get(self.security_level, SECURITY_LEVELS["team"])


class SSOAuthError(Exception):
    """SSO token 缺失、非法或已过期。"""


class SSOAuth:
    """SSO token 解析器，模式由配置决定。"""

    def __init__(self, config: Config | None = None):
        self.config = config or Config()
        self.mode = self.config.SSO_MODE
        if self.mode not in ("mock", "jwt"):
            raise ValueError(
                f"未知 sso_mode '{self.mode}'，支持 mock / jwt（config.ini [security]）"
            )

    def authenticate(self, token: str | None) -> UserContext:
        """解析 token 为用户身份；失败抛 SSOAuthError。"""
        if not token:
            raise SSOAuthError("缺少 SSO token")
        if self.mode == "mock":
            return self._parse_mock(token)
        return self._parse_jwt(token)

    def _parse_mock(self, token: str) -> UserContext:
        # 格式：user_id:name:team[:security_level]
        parts = token.split(":")
        if len(parts) < 3 or len(parts) > 4:
            raise SSOAuthError("mock token 格式应为 user_id:name:team[:security_level]")
        user_id, name, team = parts[0], parts[1], parts[2]
        level = parts[3] if len(parts) == 4 else self.config.DEFAULT_SECURITY_LEVEL
        if level not in SECURITY_LEVEL_NAMES:
            raise SSOAuthError(f"非法 security_level '{level}'")
        return UserContext(user_id=user_id, name=name, team=team, security_level=level)

    def _parse_jwt(self, token: str) -> UserContext:
        try:
            header_b64, payload_b64, signature_b64 = token.split(".")
            # 校验签名
            signing_input = f"{header_b64}.{payload_b64}".encode()
            expected = base64.urlsafe_b64encode(
                hmac.new(
                    self.config.SSO_SECRET.encode(), signing_input, hashlib.sha256
                ).digest()
            ).rstrip(b"=")
            if not hmac.compare_digest(expected, signature_b64.encode()):
                raise SSOAuthError("token 签名校验失败")
            payload = json.loads(_b64url_decode(payload_b64))
        except (ValueError, json.JSONDecodeError) as e:
            raise SSOAuthError(f"token 格式非法: {e}") from e
        if payload.get("exp") and payload["exp"] < _now():
            raise SSOAuthError("token 已过期")
        level = payload.get("security_level", self.config.DEFAULT_SECURITY_LEVEL)
        if level not in SECURITY_LEVEL_NAMES:
            raise SSOAuthError(f"非法 security_level '{level}'")
        return UserContext(
            user_id=str(payload.get("sub", "")),
            name=str(payload.get("name") or payload.get("nickname") or ""),
            team=str(payload.get("team", "")),
            security_level=level,
        )


def _b64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def _now() -> int:
    import time

    return int(time.time())


_sso_auth = SSOAuth()


def get_current_user(
    authorization: str | None = Header(default=None),
) -> UserContext:
    """FastAPI 依赖：从 Authorization 头解析当前用户；失败返回 401。"""
    token = _strip_bearer(authorization)
    try:
        return _sso_auth.authenticate(token)
    except SSOAuthError as e:
        raise HTTPException(status_code=401, detail=f"未认证或 token 无效: {e}")


def _strip_bearer(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    return token.strip()


def build_permission_filter(
    user: UserContext, requested_source: str | None = None
) -> dict:
    """生成检索强制注入的权限过滤条件（不可绕过）。

    - team：恒为用户所在团队，用户只能检索本团队文档；
    - security_level：恒为 <= 用户等级，公开/团队/机密分级可见；
    - requested_source 非空且与用户团队不一致时忽略（契约语义），
      仅记录日志，检索结果仍以 user.team 为准。

    返回的 dict 直接作为 T4 search(filter=...) 的入参。
    """
    import logging

    if requested_source and requested_source != user.team:
        logging.getLogger("internal_kb_qa.api.deps").warning(
            "用户 %s 请求越权 source_filter='%s'，已忽略，强制使用 team='%s'",
            user.user_id,
            requested_source,
            user.team,
        )
    return {
        "team": user.team,
        "security_level": {"$lte": user.security_rank()},
    }


def require_permission(user: UserContext = Depends(get_current_user)) -> UserContext:
    """路由级权限校验占位：目前所有接口对任意已认证用户开放。

    后续按接口细化（如审计接口限管理员）时在此扩展。
    """
    return user
