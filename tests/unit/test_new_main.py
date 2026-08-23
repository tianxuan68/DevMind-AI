# -*- coding: utf-8 -*-
"""集成编排（new_main）降级链路测试：T5/T6/T7 未交付时契约行为正确。"""
import pytest

import pymysql
import redis as redis_lib

from base.config import Config
from internal_kb_qa.api.deps import UserContext
from new_main import IntegratedQASystem

USER = UserContext(user_id="u001", name="测试用户", team="backend", security_level="team")


@pytest.fixture
def system(monkeypatch):
    """强制 Redis/MySQL 不可用，验证降级链路。"""

    def _raise_redis(*args, **kwargs):
        raise redis_lib.RedisError("redis down")

    def _raise_mysql(*args, **kwargs):
        raise pymysql.MySQLError("mysql down")

    monkeypatch.setattr("mysql_qa.cache.redis_client._probe_redis", lambda *a, **k: False)
    monkeypatch.setattr("mysql_qa.cache.redis_client.redis.StrictRedis", _raise_redis)
    monkeypatch.setattr("internal_kb_qa.core.ticket_service.pymysql.connect", _raise_mysql)
    return IntegratedQASystem(Config())


class TestChat:
    def test_chitchat_sync(self, system):
        result = system.query_sync("你好", None, None, USER)
        assert result.is_streaming is False
        assert result.need_human is False
        assert result.answer

    def test_chitchat_events(self, system):
        events = list(system.query_events("你是谁", None, None, USER))
        types = [e["type"] for e in events]
        assert types == ["token", "end"]
        assert events[-1]["need_human"] is False


class TestRuleClassify:
    """T6 契约：两类（通用知识/专业咨询），与基线 QueryClassifier 对齐。"""

    def test_chitchat_is_general_knowledge(self, system):
        result = system._classify("你好")
        assert result["category"] == "通用知识"
        assert result["confidence"] >= 0.9

    def test_tech_question_is_professional(self, system):
        result = system._classify("JVM 内存溢出怎么排查")
        assert result["category"] == "专业咨询"

    def test_override_detection(self, system):
        """服务策略规则独立于分类：incident/complaint 转人工，access_request 引导。"""
        assert system._check_override("生产环境宕机了") == "incident"
        assert system._check_override("我要投诉") == "complaint"
        assert system._check_override("申请数据库权限") == "access_request"
        assert system._check_override("你好") is None


class TestHumanFallback:
    def test_incident_creates_ticket(self, system):
        result = system.query_sync("生产环境宕机了", None, None, USER)
        assert result.need_human is True
        ticket = system.redis.pop_ticket()
        assert ticket is not None
        assert ticket["team"] == "backend"

    def test_complaint_creates_ticket(self, system):
        result = system.query_sync("这个系统太差了，我要投诉", None, None, USER)
        assert result.need_human is True
        assert system.redis.pop_ticket() is not None

    def test_low_confidence_rag_creates_ticket(self, system):
        """RAG 低置信度且无引用时必生成工单（验收硬指标）。"""

        def fake_rag_answer(query, history, category, filter=None):
            return {"answer": "我不确定", "sources": [], "confidence": 0.3}

        system.rag_answer = fake_rag_answer
        events = list(system.query_events("一个复杂的技术问题", None, None, USER))
        end = events[-1]
        assert end["need_human"] is True
        assert system.redis.pop_ticket() is not None

    def test_rag_answer_receives_category_and_filter(self, system):
        """T7 调用契约：(query, history, category, filter)。"""
        captured = {}

        def fake_rag_answer(query, history, category, filter=None):
            captured["category"] = category
            captured["filter"] = filter
            return {"answer": "答", "sources": [], "confidence": 0.9}

        system.rag_answer = fake_rag_answer
        list(system.query_events("JVM 内存溢出怎么排查", None, None, USER))
        assert captured["category"] == "专业咨询"
        assert captured["filter"] == {"team": "backend", "security_level": {"$lte": 1}}

    def test_rag_answer_stream_event_flow(self, system):
        """T7 流式事件流：token/end 事件透传，sources 进入 end 消息。"""

        def fake_rag_answer_stream(query, history, category, filter=None):
            yield {"type": "token", "token": "片段一"}
            yield {"type": "token", "token": "片段二"}
            yield {
                "type": "end",
                "sources": [{"title": "文档.md", "page": 1, "score": 0.9, "text": "x"}],
                "confidence": 0.95,
            }

        system.rag_answer_stream = fake_rag_answer_stream
        events = list(system.query_events("Kafka 消费积压怎么排查", None, None, USER))
        assert [e["type"] for e in events] == ["token", "token", "end"]
        assert events[-1]["sources"][0]["title"] == "文档.md"
        assert events[-1]["need_human"] is False  # 高置信度且有引用，不转人工

    def test_rag_unavailable_falls_back_to_human(self, system):
        """T7 未接入时 tech 问题走转人工兜底。"""
        events = list(system.query_events("数据库连接池参数怎么调", None, None, USER))
        end = events[-1]
        assert end["need_human"] is True
        assert system.redis.pop_ticket() is not None


class TestAccessRequest:
    def test_access_request_no_ticket(self, system):
        result = system.query_sync("我要申请数据库权限", None, None, USER)
        assert result.need_human is False
        assert "权限" in result.answer


class TestFaq:
    def test_faq_hit_returns_sources(self, system):
        def fake_faq_match(query):
            return {"answer": "标准答案", "source": "FAQ手册", "score": 0.95}

        system.faq_match = fake_faq_match
        result = system.query_sync("环境变量怎么配", None, None, USER)
        assert result.is_streaming is False
        assert result.answer == "标准答案"
        assert result.sources and result.sources[0]["title"] == "FAQ手册"

    def test_faq_hit_caches_answer(self, system):
        def fake_faq_match(query):
            return {"answer": "缓存答案", "source": "", "score": 0.9}

        system.faq_match = fake_faq_match
        system.query_sync("重复问题", None, None, USER)
        # 清掉上游，走 Redis 热缓存
        system.faq_match = None
        result = system.query_sync("重复问题", None, None, USER)
        assert result.answer == "缓存答案"

    def test_tech_no_faq_marks_streaming(self, system):
        result = system.query_sync("如何排查接口超时", None, None, USER)
        assert result.is_streaming is True


class TestSessionHistory:
    def test_history_kept_and_trimmed(self, system):
        """FAQ 命中场景更新会话历史；历史保留最近 5 轮。"""

        def fake_faq_match(query):
            return {"answer": f"答案:{query}", "source": "", "score": 0.9}

        system.faq_match = fake_faq_match
        session_id = "sess-1"
        for i in range(7):
            system.query_sync(f"问题{i}", session_id, None, USER)
        history = system.redis.get_session(session_id)
        assert len(history) == 5
        assert history[-1]["question"] == "问题6"
