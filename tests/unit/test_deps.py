# -*- coding: utf-8 -*-
"""SSO 身份解析与权限过滤注入测试（T8 检验：SSO 身份解析正确性、越权命中数为 0）。"""
import base64
import hashlib
import hmac
import json
import time

import pytest

from internal_kb_qa.api.deps import (
    SSOAuth,
    SSOAuthError,
    UserContext,
    build_permission_filter,
    _strip_bearer,
)


class TestMockMode:
    def setup_method(self):
        self.auth = SSOAuth()

    def test_parse_full_token(self):
        user = self.auth.authenticate("u001:张三:backend:secret")
        assert user.user_id == "u001"
        assert user.name == "张三"
        assert user.team == "backend"
        assert user.security_level == "secret"

    def test_parse_without_level_uses_default(self):
        user = self.auth.authenticate("u002:李四:ops")
        assert user.security_level == "team"  # config.ini default_security_level

    def test_parse_empty_token_rejected(self):
        with pytest.raises(SSOAuthError):
            self.auth.authenticate(None)
        with pytest.raises(SSOAuthError):
            self.auth.authenticate("")

    def test_parse_bad_format_rejected(self):
        with pytest.raises(SSOAuthError):
            self.auth.authenticate("onlytwo:parts")
        with pytest.raises(SSOAuthError):
            self.auth.authenticate("a:b:c:invalid_level")

    def test_security_rank(self):
        assert UserContext("u", "n", "t", "public").security_rank() == 0
        assert UserContext("u", "n", "t", "team").security_rank() == 1
        assert UserContext("u", "n", "t", "secret").security_rank() == 2


def _make_jwt(payload: dict, secret: str) -> str:
    def b64(data: bytes) -> str:
        return base64.urlsafe_b64encode(data).rstrip(b"=").decode()

    header = b64(json.dumps({"alg": "HS256"}).encode())
    body = b64(json.dumps(payload).encode())
    signing_input = f"{header}.{body}".encode()
    signature = b64(hmac.new(secret.encode(), signing_input, hashlib.sha256).digest())
    return f"{header}.{body}.{signature}"


class TestJwtMode:
    def setup_method(self):
        self.secret = "test-secret"
        self.auth = SSOAuth()
        self.auth.mode = "jwt"
        self.auth.config.SSO_SECRET = self.secret

    def test_valid_token(self):
        token = _make_jwt(
            {"sub": "u9", "name": "王五", "team": "data", "security_level": "public"},
            self.secret,
        )
        user = self.auth.authenticate(token)
        assert user.team == "data"
        assert user.security_level == "public"

    def test_wrong_signature_rejected(self):
        token = _make_jwt({"sub": "u9", "name": "王五", "team": "data"}, "other-secret")
        with pytest.raises(SSOAuthError):
            self.auth.authenticate(token)

    def test_expired_token_rejected(self):
        token = _make_jwt(
            {"sub": "u9", "name": "王五", "team": "data", "exp": int(time.time()) - 10},
            self.secret,
        )
        with pytest.raises(SSOAuthError):
            self.auth.authenticate(token)

    def test_malformed_token_rejected(self):
        with pytest.raises(SSOAuthError):
            self.auth.authenticate("not-a-jwt")


class TestBearerExtraction:
    def test_valid_bearer(self):
        assert _strip_bearer("Bearer abc123") == "abc123"

    def test_missing_header(self):
        assert _strip_bearer(None) is None

    def test_wrong_scheme(self):
        assert _strip_bearer("Basic abc") is None

    def test_empty_token(self):
        assert _strip_bearer("Bearer ") is None


class TestPermissionFilter:
    def test_force_own_team(self):
        user = UserContext("u1", "n", "backend", "team")
        filt = build_permission_filter(user)
        assert filt["team"] == "backend"
        assert filt["security_level"] == {"$lte": 1}

    def test_secret_user_rank(self):
        user = UserContext("u1", "n", "infra", "secret")
        assert build_permission_filter(user)["security_level"] == {"$lte": 2}

    def test_cross_team_source_filter_ignored(self):
        """越权请求：source_filter=frontend 被忽略，过滤条件恒为用户团队。"""
        user = UserContext("u1", "n", "backend", "team")
        filt = build_permission_filter(user, requested_source="frontend")
        assert filt["team"] == "backend"
        assert "frontend" not in str(filt)

    def test_same_team_source_filter_kept(self):
        user = UserContext("u1", "n", "backend", "team")
        filt = build_permission_filter(user, requested_source="backend")
        assert filt["team"] == "backend"
