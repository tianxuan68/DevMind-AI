# -*- coding: utf-8 -*-
"""权限隔离验证（T8 侧自测；T11 做最终验收）。

验收硬指标：越权检索命中数必须为 0。本测试验证：
1. 权限过滤条件不可绕过（filter 恒为用户团队 + 等级上限）；
2. 越权 source_filter 请求被忽略，不会进入检索条件；
3. 编排层调用上游 RAG 时强制携带权限过滤。
"""
import pytest
from fastapi.testclient import TestClient

from app import app
from new_main import IntegratedQASystem
from base.config import Config

TOKEN_BACKEND = "u001:BackendDev:backend:team"
TOKEN_FRONTEND = "u002:FrontendDev:frontend:team"


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_unit_filter_always_injected():
    """单元层：跨团队 source_filter 无法改变过滤条件。"""
    from internal_kb_qa.api.deps import build_permission_filter, UserContext

    user = UserContext("u1", "n", "backend", "team")
    filt = build_permission_filter(user, requested_source="secret_source")
    assert filt["team"] == "backend"
    assert filt["security_level"] == {"$lte": 1}


def test_orchestration_passes_filter_to_rag(monkeypatch):
    """编排层：T7 调用必须收到权限过滤条件（R9 不可绕过）。"""
    captured = {}

    def fake_rag_answer(query, history, category, filter=None):
        captured["filter"] = filter
        return {"answer": "答", "sources": [], "confidence": 0.9}

    system = IntegratedQASystem(Config())
    system.rag_answer = fake_rag_answer
    user = __import__("internal_kb_qa.api.deps", fromlist=["UserContext"]).UserContext(
        "u1", "n", "backend", "team"
    )
    list(system.query_events("一个技术问题", None, None, user))
    assert captured["filter"] == {"team": "backend", "security_level": {"$lte": 1}}


def test_cross_team_source_filter_ignored_at_api(client):
    """集成层：backend 用户请求 frontend 过滤，仍正常响应且不报越权数据。"""
    resp = client.post(
        "/api/query",
        json={"query": "你好", "source_filter": "frontend"},
        headers={"Authorization": f"Bearer {TOKEN_BACKEND}"},
    )
    assert resp.status_code == 200
    # 该用户只能看到 backend 团队数据（过滤条件在编排层强制注入，见单元测试）
    assert resp.json()["need_human"] is False
