# -*- coding: utf-8 -*-
"""API 集成测试：契约字段、状态码、SSO 401、WS 流式时序（TestClient 全链路）。"""
import re

import pytest
from fastapi.testclient import TestClient

from app import app

TOKEN = "u001:TestUser:backend:team"


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


class TestHealth:
    def test_health_ok(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "healthy"}


class TestSSO:
    def test_query_without_token_401(self, client):
        resp = client.post("/api/query", json={"query": "你好"})
        assert resp.status_code == 401

    def test_query_bad_token_401(self, client):
        resp = client.post(
            "/api/query",
            json={"query": "你好"},
            headers={"Authorization": "Bearer badtoken"},
        )
        assert resp.status_code == 401

    def test_sources_without_token_401(self, client):
        assert client.get("/api/sources").status_code == 401


class TestCreateSession:
    def test_returns_uuid(self, client):
        resp = client.post("/api/create_session", headers={"Authorization": f"Bearer {TOKEN}"})
        assert resp.status_code == 200
        session_id = resp.json()["session_id"]
        assert re.fullmatch(r"[0-9a-f-]{36}", session_id)


class TestQuery:
    def test_chitchat_contract_fields(self, client):
        resp = client.post(
            "/api/query",
            json={"query": "你好"},
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert set(body) == {
            "answer", "is_streaming", "need_human", "sources", "session_id", "processing_time",
        }
        assert body["is_streaming"] is False
        assert isinstance(body["sources"], list)
        assert isinstance(body["processing_time"], float)

    def test_incident_need_human(self, client):
        resp = client.post(
            "/api/query",
            json={"query": "生产环境服务宕机了"},
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        assert resp.status_code == 200
        assert resp.json()["need_human"] is True

    def test_tech_marks_streaming(self, client):
        resp = client.post(
            "/api/query",
            json={"query": "JVM 内存溢出怎么排查"},
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        assert resp.status_code == 200
        assert resp.json()["is_streaming"] is True


class TestSources:
    def test_returns_valid_sources(self, client):
        resp = client.get("/api/sources", headers={"Authorization": f"Bearer {TOKEN}"})
        assert resp.status_code == 200
        sources = resp.json()["sources"]
        assert "backend" in sources
        assert "infra" in sources


class TestFeedback:
    def test_rating_validation_422(self, client):
        resp = client.post(
            "/api/feedback",
            json={"session_id": "s1", "query": "q", "rating": 6},
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        assert resp.status_code == 422

    def test_feedback_without_ticket(self, client):
        resp = client.post(
            "/api/feedback",
            json={"session_id": "s1", "query": "q", "rating": 5, "comment": "不错"},
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "success"
        assert body["ticket_id"] is None

    def test_feedback_need_human_returns_ticket(self, client):
        resp = client.post(
            "/api/feedback",
            json={
                "session_id": "s2",
                "query": "问题没解决，需要人工",
                "rating": 1,
                "need_human": True,
            },
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        assert resp.status_code == 200
        ticket_id = resp.json()["ticket_id"]
        assert ticket_id and ticket_id.startswith("TK")


class TestStream:
    def test_full_chat_flow(self, client):
        with client.websocket_connect("/api/stream") as ws:
            ws.send_json({"type": "auth", "token": TOKEN})
            start = ws.receive_json()
            assert start["type"] == "start"
            assert start["session_id"]

            ws.send_json({"type": "query", "query": "你好", "session_id": start["session_id"]})
            tokens = []
            while True:
                msg = ws.receive_json()
                if msg["type"] == "end":
                    assert msg["is_complete"] is True
                    assert "processing_time" in msg
                    break
                assert msg["type"] == "token"
                tokens.append(msg["token"])
            assert "".join(tokens)

    def test_auth_failure_rejected(self, client):
        with client.websocket_connect("/api/stream") as ws:
            ws.send_json({"type": "auth", "token": "bad-token"})
            msg = ws.receive_json()
            assert msg["type"] == "error"
