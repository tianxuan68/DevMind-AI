"""集成编排入口（T8）。

主链路：
意图分类(T6) -> FAQ 精确匹配(T5) -> 检索生成(T4/T7) -> 转人工兜底。

上游模块按任务分工文档约定的接口签名探测式接入：
- T5 ``faq_match(query) -> FAQHit | None``（internal_kb_qa.core.faq_matcher）
- T6 ``classify(query) -> Classification``（internal_kb_qa.core.intent_classifier）
  七类：tech / access_request / incident / ticket_inquiry /
  complaint_suggestion / policy_general / chitchat(=common)
- T7 ``rag_answer(query, history, category, filter=None) -> RAGResult`` /
  ``rag_answer_stream(query, history, category, filter=None) -> Generator[dict]``
  （internal_kb_qa.core.rag_generator；``category`` 为 T6 七类之一，供检索策略
  路由；``filter`` 为 T8 注入的权限过滤条件，T7 实现时必须接受并在检索链路
  强制使用，越权命中数必须为 0；流式产出 token/end 事件，end 携带
  sources/confidence）

上游未交付时自动降级（规则意图分类 + FAQ 热缓存 + 转人工兜底），
保证端到端契约可跑可测；算法组交付后无需改动 T8 调用方。

职责：会话历史（Redis，最近 5 轮）、LLM 故障降级 FAQ 直回、incident/
投诉/低置信度自动建工单（ticket_service）、ticket_inquiry 工单进度查询。
"""
import logging
import re
import time
import uuid
from dataclasses import dataclass, field

from base.config import Config
from internal_kb_qa.api.deps import UserContext, build_permission_filter
from internal_kb_qa.core.ticket_service import TicketService
from mysql_qa.cache.redis_client import RedisClient

logger = logging.getLogger("internal_kb_qa.new_main")

CHITCHAT_REPLIES = {
    "greet": "你好！我是企业内部技术知识库智能问答助手，你可以问我环境配置、权限申请、常见报错等技术问题。",
    "who": "我是企业内部技术知识库智能问答助手，基于企业授权文档提供技术问答，回答均附文档出处。",
    "thanks": "不客气，有需要随时问我！",
    "bye": "再见，有需要随时找我！",
}

CHITCHAT_PATTERNS = {
    "greet": r"^(你好|您好|hi|hello|嗨)",
    "who": r"^(你是谁|你叫什么|介绍一下你|who are you)",
    "thanks": r"^(谢谢|感谢|多谢)",
    "bye": r"^(再见|拜拜|88|bye)",
}

# 意图分类降级规则（T6 交付前使用；命中即高置信度）。
# 七类：tech / access_request / incident / ticket_inquiry /
#       complaint_suggestion / policy_general / chitchat(=common 闲聊)
# 顺序即优先级：先闲聊，再具体意图（故障/投诉优先），默认 tech 保守路由。
RULE_CATEGORY_PATTERNS = {
    "incident": ["故障", "宕机", "挂了", "事故", "数据丢失", "紧急", "生产环境", "不可用", "报障", "告警"],
    "complaint_suggestion": ["投诉", "差评", "不满意", "太差", "垃圾系统", "吐槽", "建议", "意见", "改进"],
    "access_request": [r"申请.*(权限|账号)", r"开通.*(账号|权限)", r"权限申请", r"账号申请", r"授权"],
    "ticket_inquiry": [r"工单.*(进度|状态|查询|处理|到哪)", r"进度查询", r"我的工单", r"工单号"],
    "policy_general": ["制度", "规范", "规定", "政策", "流程", "报销", "请假", "考勤", "规章制度"],
}

# 投诉关键词（complaint_suggestion 类内细分）：命中按投诉转人工建单，否则按建议致谢
COMPLAINT_KEYWORDS = ("投诉", "差评", "不满意", "太差", "垃圾", "吐槽")

# T6 二类中文标签 → T8 路由英文 slug（不改动 intent_classifier 契约）
_T6_CATEGORY_TO_ROUTE = {
    "技术咨询": "tech",
    "通用知识": "policy_general",
}

ACCESS_REQUEST_REPLY = (
    "权限/账号申请请走内部审批流程：联系您的直属主管或系统管理员提交权限申请工单。"
)

SUGGESTION_REPLY = (
    "感谢您的建议，我们已记录并将反馈给相关团队。如需进一步沟通，可在反馈中留下联系方式。"
)


@dataclass
class QueryResult:
    """非流式问答结果（/api/query 契约字段）。"""

    answer: str
    is_streaming: bool
    need_human: bool
    sources: list = field(default_factory=list)
    session_id: str = ""


class IntegratedQASystem:
    def __init__(self, config: Config | None = None):
        self.config = config or Config()
        self.redis = RedisClient(self.config)
        self.ticket_service = TicketService(self.config, self.redis)
        self._load_upstream()

    # ---- 上游模块探测接入（T5/T6/T7，未交付时降级） ----

    def _load_upstream(self) -> None:
        self.faq_match = None
        self.classify = None
        self.rag_answer = None
        self.rag_answer_stream = None
        try:
            from internal_kb_qa.core.faq_matcher import faq_match

            self.faq_match = faq_match
            logger.info("T5 faq_match 已接入")
        except Exception as e:
            logger.warning("T5 faq_match 未接入（%s），FAQ 走 Redis 热缓存降级", e)
        try:
            from internal_kb_qa.core.intent_classifier import classify

            self.classify = classify
            logger.info("T6 classify 已接入")
        except Exception as e:
            logger.warning("T6 classify 未接入（%s），意图分类走规则降级", e)
        try:
            from internal_kb_qa.core.rag_generator import rag_answer, rag_answer_stream

            self.rag_answer = rag_answer
            self.rag_answer_stream = rag_answer_stream
            logger.info("T7 rag_answer 已接入")
        except Exception as e:
            logger.warning("T7 rag_answer 未接入（%s），RAG 走转人工兜底降级", e)

    # ---- 意图分类（T6 优先，规则降级） ----

    def _classify(self, query: str) -> dict:
        """返回 {category, confidence}；T6 未接入时用规则降级。

        细粒度意图（闲聊/故障/投诉/权限/工单）优先走规则，保证 T8 七类路由；
        规则落在 tech 时再调用 T6 二分类，将「通用知识」映射为 policy_general。
        """
        rule = self._rule_classify(query)
        if rule["category"] != "tech":
            return rule

        if self.classify is not None:
            try:
                result = self.classify(query)
                category, confidence = self._normalize_classification(result)
                if category:
                    mapped = _T6_CATEGORY_TO_ROUTE.get(category, category)
                    return {"category": mapped, "confidence": confidence}
            except Exception as e:
                logger.error("T6 classify 调用失败: %s", e)
        return rule

    @staticmethod
    def _normalize_classification(result) -> tuple[str, float]:
        """兼容 Classification 对象与 dict。"""
        if result is None:
            return "", 0.0
        if hasattr(result, "category"):
            return str(getattr(result, "category", "") or ""), float(
                getattr(result, "confidence", 0.6) or 0.6
            )
        if isinstance(result, dict):
            return str(result.get("category") or ""), float(result.get("confidence") or 0.6)
        return "", 0.0

    def _rule_classify(self, query: str) -> dict:
        """七类降级分类（T6 交付前使用）。

        顺序：chitchat（闲聊）-> incident（故障）-> complaint_suggestion（投诉/建议）
        -> access_request（权限/账号）-> ticket_inquiry（工单查询）
        -> policy_general（制度）-> 默认 tech（低置信度保守路由）。
        """
        for pattern in CHITCHAT_PATTERNS.values():
            if re.match(pattern, query, re.IGNORECASE):
                return {"category": "chitchat", "confidence": 0.9}
        for category, patterns in RULE_CATEGORY_PATTERNS.items():
            if any(re.search(p, query) for p in patterns):
                return {"category": category, "confidence": 0.9}
        return {"category": "tech", "confidence": 0.6}

    # ---- 会话历史（Redis，最近 5 轮） ----

    def _get_history(self, session_id: str | None) -> list:
        if not session_id:
            return []
        return self.redis.get_session(session_id)

    def _update_history(self, session_id: str, question: str, answer: str) -> None:
        history = self.redis.get_session(session_id)
        history.append({"question": question, "answer": answer})
        self.redis.set_session(session_id, history[-5:])

    # ---- 主链路 ----

    def query_sync(
        self,
        query: str,
        session_id: str | None,
        source_filter: str | None,
        user: UserContext,
    ) -> QueryResult:
        """非流式查询：七类意图路由；需要 RAG 时标记流式。

        路由：chitchat 模板直答 / incident 转人工建单 /
        complaint_suggestion 投诉建单·建议致谢 / access_request 引导审批 /
        ticket_inquiry 工单进度查询 / tech·policy_general FAQ -> RAG。
        """
        if not session_id:
            session_id = str(uuid.uuid4())
        category = self._classify(query)["category"]

        # 闲聊：模板直答，不检索
        if category == "chitchat":
            answer = self._chitchat_reply(query)
            self._update_history(session_id, query, answer)
            return QueryResult(answer=answer, is_streaming=False, need_human=False,
                               session_id=session_id)

        # 故障上报：不硬答，转人工建单
        if category == "incident":
            answer, need_human = self._human_fallback(query, session_id, user, "incident")
            self._update_history(session_id, query, answer)
            return QueryResult(answer=answer, is_streaming=False, need_human=need_human,
                               session_id=session_id)

        # 投诉/建议：投诉转人工建单；建议致谢
        if category == "complaint_suggestion":
            if any(kw in query for kw in COMPLAINT_KEYWORDS):
                answer, need_human = self._human_fallback(
                    query, session_id, user, "complaint"
                )
            else:
                answer, need_human = SUGGESTION_REPLY, False
            self._update_history(session_id, query, answer)
            return QueryResult(answer=answer, is_streaming=False, need_human=need_human,
                               session_id=session_id)

        # 权限/账号申请：引导审批流程（不走工单）
        if category == "access_request":
            self._update_history(session_id, query, ACCESS_REQUEST_REPLY)
            return QueryResult(answer=ACCESS_REQUEST_REPLY, is_streaming=False,
                               need_human=False, session_id=session_id)

        # 工单/进度查询：查用户最近工单状态
        if category == "ticket_inquiry":
            answer = self._ticket_inquiry_reply(user)
            self._update_history(session_id, query, answer)
            return QueryResult(answer=answer, is_streaming=False, need_human=False,
                               session_id=session_id)

        # tech / policy_general：FAQ 精确匹配
        faq_hit = self._faq_match(query)
        if faq_hit:
            answer = faq_hit["answer"]
            sources = [{
                "title": faq_hit.get("source", ""),
                "page": None,
                "score": faq_hit.get("score", 1.0),
                "text": "",
            }] if faq_hit.get("source") else []
            self.redis.set_answer(query, answer)
            self._update_history(session_id, query, answer)
            return QueryResult(answer=answer, is_streaming=False, need_human=False,
                               sources=sources, session_id=session_id)

        # 需要 RAG 主链路：提示走流式接口
        return QueryResult(answer="请使用WebSocket接口获取流式响应", is_streaming=True,
                           need_human=False, session_id=session_id)

    def query_events(
        self,
        query: str,
        session_id: str | None,
        source_filter: str | None,
        user: UserContext,
    ):
        """流式主链路生成器，产出事件 dict：{type: token|end, ...}。

        - token: {"type": "token", "token": str}
        - end:   {"type": "end", "is_complete", "sources", "need_human"}
        供 WS /api/stream 逐条转发；处理失败抛异常，由调用方发 error 消息。
        """
        if not session_id:
            session_id = str(uuid.uuid4())
        history = self._get_history(session_id)
        category = self._classify(query)["category"]

        # 闲聊：模板直答，不检索
        if category == "chitchat":
            answer = self._chitchat_reply(query)
            self._update_history(session_id, query, answer)
            yield {"type": "token", "token": answer}
            yield {"type": "end", "is_complete": True, "sources": [], "need_human": False}
            return

        # 故障上报：不硬答，转人工建单
        if category == "incident":
            answer, need_human = self._human_fallback(query, session_id, user, "incident")
            self._update_history(session_id, query, answer)
            yield {"type": "token", "token": answer}
            yield {"type": "end", "is_complete": True, "sources": [], "need_human": need_human}
            return

        # 投诉/建议：投诉转人工建单；建议致谢
        if category == "complaint_suggestion":
            if any(kw in query for kw in COMPLAINT_KEYWORDS):
                answer, need_human = self._human_fallback(
                    query, session_id, user, "complaint"
                )
            else:
                answer, need_human = SUGGESTION_REPLY, False
            self._update_history(session_id, query, answer)
            yield {"type": "token", "token": answer}
            yield {"type": "end", "is_complete": True, "sources": [], "need_human": need_human}
            return

        # 权限/账号申请：引导审批流程（不走工单）
        if category == "access_request":
            self._update_history(session_id, query, ACCESS_REQUEST_REPLY)
            yield {"type": "token", "token": ACCESS_REQUEST_REPLY}
            yield {"type": "end", "is_complete": True, "sources": [], "need_human": False}
            return

        # 工单/进度查询：查用户最近工单状态
        if category == "ticket_inquiry":
            answer = self._ticket_inquiry_reply(user)
            self._update_history(session_id, query, answer)
            yield {"type": "token", "token": answer}
            yield {"type": "end", "is_complete": True, "sources": [], "need_human": False}
            return

        # tech / policy_general：FAQ 命中即秒回
        faq_hit = self._faq_match(query)
        if faq_hit:
            answer = faq_hit["answer"]
            sources = [{
                "title": faq_hit.get("source", ""),
                "page": None,
                "score": faq_hit.get("score", 1.0),
                "text": "",
            }] if faq_hit.get("source") else []
            self.redis.set_answer(query, answer)
            self._update_history(session_id, query, answer)
            yield {"type": "token", "token": answer}
            yield {"type": "end", "is_complete": True, "sources": sources, "need_human": False}
            return

        # RAG 主链路（T7）；LLM 故障时降级：FAQ 直回 -> 转人工
        sources, confidence, need_human = [], 0.0, False
        collected = ""
        try:
            for event in self._rag_stream(query, history, category, user):
                if event["type"] == "token":
                    collected += event["token"]
                    yield event
                elif event["type"] == "end":
                    sources = event.get("sources", [])
                    confidence = event.get("confidence", 0.0)
        except Exception as e:
            logger.error("RAG 链路失败，降级 FAQ 直回: %s", e)
            faq_retry = self._faq_match(query)
            if faq_retry:
                yield {"type": "token", "token": faq_retry["answer"]}
                collected = faq_retry["answer"]
                sources = [{
                    "title": faq_retry.get("source", ""),
                    "page": None,
                    "score": faq_retry.get("score", 1.0),
                    "text": "",
                }] if faq_retry.get("source") else []
            else:
                answer, _ = self._human_fallback(query, session_id, user, "low_confidence")
                yield {"type": "token", "token": answer}
                collected = answer
                need_human = True

        # 低置信度兜底：转人工并生成工单（验收：低置信度必生成工单）
        if not need_human and confidence < self.config.CONFIDENCE_THRESHOLD and not sources:
            need_human = True
            self.ticket_service.create_ticket(
                session_id, query, user.user_id, user.team, reason="low_confidence"
            )
            logger.info("低置信度回答触发转人工: session=%s", session_id)

        self._update_history(session_id, query, collected)
        yield {
            "type": "end",
            "is_complete": True,
            "sources": sources,
            "need_human": need_human,
        }

    # ---- 链路组件 ----

    def _chitchat_reply(self, query: str) -> str:
        for reply_key, pattern in CHITCHAT_PATTERNS.items():
            if re.match(pattern, query, re.IGNORECASE):
                return CHITCHAT_REPLIES[reply_key]
        return CHITCHAT_REPLIES["greet"]

    def _faq_match(self, query: str) -> dict | None:
        """FAQ 精确匹配：T5 优先；T5 未接入时走 Redis 热缓存。"""
        if self.faq_match is not None:
            try:
                hit = self.faq_match(query)
                if hit:
                    logger.info("FAQ 命中: %s", query)
                    return self._faq_hit_to_dict(hit)
            except Exception as e:
                logger.error("T5 faq_match 调用失败: %s", e)
        cached = self.redis.get_answer(query)
        if cached:
            return {"answer": cached, "source": "", "score": 1.0}
        return None

    @staticmethod
    def _faq_hit_to_dict(hit) -> dict:
        """兼容 FAQHit dataclass 与 dict。"""
        if isinstance(hit, dict):
            return hit
        return {
            "answer": getattr(hit, "answer", "") or "",
            "source": getattr(hit, "source", "") or "",
            "score": float(getattr(hit, "score", 1.0) or 1.0),
        }

    def _ticket_inquiry_reply(self, user: UserContext) -> str:
        """工单/进度查询：返回用户最近工单状态；无工单时引导转人工。"""
        from internal_kb_qa.core.ticket_service import TICKET_STATUS_LABELS

        tickets = self.ticket_service.get_recent_tickets(user.user_id, limit=3)
        if not tickets:
            return "未查询到您的工单。如需人工帮助，可在反馈中勾选转人工，我们会尽快处理。"
        lines = ["您最近的工单状态："]
        for t in tickets:
            label = TICKET_STATUS_LABELS.get(t["status"], t["status"])
            lines.append(f"- {t['ticket_no']}（{t['reason']}）：{label}")
        return "\n".join(lines)

    def _rag_stream(
        self, query: str, history: list, category: str, user: UserContext
    ):
        """T7 生成链路：优先 rag_answer_stream 事件流，其次 rag_answer 一次性模拟流式。

        T7 契约（与算法组对齐）：
            rag_answer(query, history, category, filter=None) -> RAGResult
            rag_answer_stream(query, history, category, filter=None) -> Generator[dict]
        - ``filter`` 为 T8 注入的权限过滤条件（R9 硬指标：越权命中数=0），
          T7 必须接受并在检索链路强制使用；缺失时 T8 告警并走兼容调用（仅联调期）。
        - ``rag_answer_stream`` 产出 {"type": "token"|"end", ...} 事件，
          end 事件携带 sources / confidence；兼容纯 str token 流（无引用信息时
          补调 rag_answer 获取 sources，属过渡降级）。
        """
        permission_filter = build_permission_filter(user)
        if self.rag_answer_stream is not None:
            saw_end = False
            try:
                stream = self.rag_answer_stream(
                    query, history, category, filter=permission_filter
                )
            except TypeError:
                logger.warning("T7 rag_answer_stream 未接受 filter 参数，检索未注入权限过滤")
                stream = self.rag_answer_stream(query, history, category)
            for item in stream:
                if isinstance(item, str):
                    yield {"type": "token", "token": item}
                elif isinstance(item, dict) and item.get("type") == "token":
                    yield item
                elif isinstance(item, dict) and item.get("type") == "end":
                    saw_end = True
                    yield item
            if not saw_end:
                # 纯 str token 流：补调非流式接口获取引用与置信度（过渡降级）
                logger.warning("T7 rag_answer_stream 未产出 end 事件，补调 rag_answer 获取引用")
                yield from self._rag_answer_once(
                    query, history, category, permission_filter, stream_tokens=False
                )
            return
        if self.rag_answer is not None:
            yield from self._rag_answer_once(
                query, history, category, permission_filter, stream_tokens=True
            )
            return
        raise RuntimeError("T7 RAG 主链路未接入")

    def _rag_answer_once(
        self,
        query: str,
        history: list,
        category: str,
        permission_filter: dict,
        stream_tokens: bool,
    ):
        """调用 T7 非流式 rag_answer 并转成 token/end 事件；兼容缺 filter 的旧签名。"""
        if self.rag_answer is None:
            yield {"type": "end", "sources": [], "confidence": 0.0}
            return
        try:
            result = self.rag_answer(query, history, category, filter=permission_filter)
        except TypeError:
            logger.warning("T7 rag_answer 未接受 filter 参数，检索未注入权限过滤")
            result = self.rag_answer(query, history, category)
        answer, sources, confidence = self._normalize_rag_result(result)
        if stream_tokens and answer:
            yield {"type": "token", "token": answer}
        yield {"type": "end", "sources": sources, "confidence": confidence}

    @staticmethod
    def _normalize_rag_result(result) -> tuple[str, list, float]:
        """兼容 RAGResult dataclass 与 dict。"""
        if result is None:
            return "", [], 0.0
        if hasattr(result, "answer"):
            raw_sources = getattr(result, "sources", None) or []
            sources = []
            for src in raw_sources:
                if isinstance(src, dict):
                    sources.append(src)
                else:
                    sources.append({
                        "title": getattr(src, "title", "") or "",
                        "page": getattr(src, "page", None),
                        "score": float(getattr(src, "score", 0.0) or 0.0),
                        "text": getattr(src, "text", "") or "",
                    })
            return (
                getattr(result, "answer", "") or "",
                sources,
                float(getattr(result, "confidence", 0.0) or 0.0),
            )
        if isinstance(result, dict):
            return (
                result.get("answer", "") or "",
                result.get("sources", []) or [],
                float(result.get("confidence", 0.0) or 0.0),
            )
        return "", [], 0.0

    def _human_fallback(
        self, query: str, session_id: str, user: UserContext, reason: str
    ) -> tuple[str, bool]:
        """转人工兜底：创建工单并返回引导文案（验收：兜底必生成工单）。"""
        self.ticket_service.create_ticket(
            session_id, query, user.user_id, user.team, reason=reason
        )
        logger.info("转人工兜底触发: session=%s reason=%s", session_id, reason)
        return "该问题已转人工处理，我们会尽快联系您，请耐心等待。", True


def create_system() -> IntegratedQASystem:
    """应用级单例入口（app.py lifespan 调用）。"""
    return IntegratedQASystem()
