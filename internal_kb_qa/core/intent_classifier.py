"""T6 意图分类与路由（LLM + Prompt few-shot，不再训练 BERT）。

对外接口：
    classify(query: str) -> Classification

分类类别：
    - tech：技术咨询
    - access_request：权限/账号申请
    - incident：故障上报
    - ticket_inquiry：工单/进度查询
    - complaint_suggestion：投诉/建议
    - policy_general：制度/通用知识
    - common：闲聊

路由约定：
    - 置信度低于 LOW_CONFIDENCE_THRESHOLD 时一律按 tech 保守路由到带引用的 RAG 主链路；
    - LLM 调用失败、超时或返回格式非法时降级返回 tech 并记录日志，保证主链路不中断。
"""

from __future__ import annotations

import json
import logging
import os
import re

from pydantic import BaseModel, Field

try:  # 项目根通用日志（base/logger.py，输出到 stdout）
    from base.logger import logger
except ImportError:  # 独立运行时兜底，避免无 handler 导致日志不可见
    logger = logging.getLogger("devmind-ai")

try:  # 项目根配置（base/config.py，读取 config.ini 的 [llm] 段）
    from base.config import Config
except ImportError:
    Config = None

try:  # DashScope 走 OpenAI 兼容协议，依赖 openai SDK
    from openai import OpenAI
except ImportError:
    OpenAI = None

# ---------------------------------------------------------------------------
# 常量配置
# ---------------------------------------------------------------------------

# 分类类别（对外契约取值）
CATEGORY_TECH = "tech"
CATEGORY_ACCESS_REQUEST = "access_request"
CATEGORY_INCIDENT = "incident"
CATEGORY_TICKET_INQUIRY = "ticket_inquiry"
CATEGORY_COMPLAINT_SUGGESTION = "complaint_suggestion"
CATEGORY_POLICY_GENERAL = "policy_general"
CATEGORY_COMMON = "common"
VALID_CATEGORIES = frozenset({
    CATEGORY_TECH,
    CATEGORY_ACCESS_REQUEST,
    CATEGORY_INCIDENT,
    CATEGORY_TICKET_INQUIRY,
    CATEGORY_COMPLAINT_SUGGESTION,
    CATEGORY_POLICY_GENERAL,
    CATEGORY_COMMON,
})

# 低置信度保守路由阈值：confidence < 阈值时按 tech 处理
LOW_CONFIDENCE_THRESHOLD = float(os.getenv("INTENT_CONFIDENCE_THRESHOLD", "0.6"))

# LLM 调用参数
LLM_TIMEOUT_SECONDS = float(os.getenv("INTENT_LLM_TIMEOUT", "10"))  # 单次调用超时（秒）
LLM_MAX_TOKENS = int(os.getenv("INTENT_LLM_MAX_TOKENS", "200"))
LLM_TEMPERATURE = 0.0  # 分类任务要求确定性输出
DEFAULT_MODEL = "qwen3-max"
DEFAULT_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"

# ---------------------------------------------------------------------------
# T6 few-shot Prompt 模板
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """你是企业内部知识库的意图分类助手。
你的任务是根据用户的核心诉求，将问题严格归入以下七类之一：

分类定义：
- "tech"（技术咨询）：部署、配置、代码、接口、性能、一般报错排查等技术实操问题。
- "access_request"（权限/账号申请）：申请或开通账号、系统权限、数据库权限、VPN、Git 权限等。
- "incident"（故障上报）：报告正在发生或已经发生的线上事故、宕机、数据异常、P0/P1、发布失败等故障。
- "ticket_inquiry"（工单/进度查询）：查询已有工单的状态、处理进度、负责人，或催促处理。
- "complaint_suggestion"（投诉/建议）：表达对服务或答复的不满、投诉，或提出改进意见和建议。
- "policy_general"（制度/通用知识）：报销、年假、福利、入职等公司制度，以及行业概念、非实操知识。
- "common"（闲聊）：寒暄、天气、无关话题等不属于业务知识问答的内容。

边界规则：
- 根据核心诉求分类，不要只按关键词分类。
- 用户要申请/开通权限，即使提到 Git、数据库等技术名词，也归 access_request。
- 用户报告线上服务不可用、数据异常、发布失败等事故，归 incident；咨询一般报错的解决方法归 tech。
- 只有在查询已经提交的工单时才归 ticket_inquiry；新问题本身按其诉求归类。
- 制度流程和非技术概念知识归 policy_general；纯寒暄或无关话题归 common。
- 同时包含多个意图时，选择用户最希望当前得到处理的主要意图。
- 无法确定时优先归 tech，以便进入 RAG 主链路。

输出要求：
- 只输出一个 JSON 对象，字段为 category、confidence；
- category 只能是 "tech"、"access_request"、"incident"、"ticket_inquiry"、
  "complaint_suggestion"、"policy_general"、"common" 之一；
- confidence 为 0 到 1 的浮点数，表示分类置信度；
- 不要输出 JSON 之外的任何文字、解释或 Markdown 代码块。"""

# few-shot 示例（覆盖七类及易混淆边界，assistant 侧输出为合法 JSON）
FEW_SHOT_EXAMPLES: tuple[tuple[str, dict], ...] = (
    (
        "本地启动 Spring Boot 服务报 Error creating bean with name 'dataSource'，怎么排查？",
        {"category": CATEGORY_TECH, "confidence": 0.97},
    ),
    (
        "帮我申请生产数据库的只读权限。",
        {"category": CATEGORY_ACCESS_REQUEST, "confidence": 0.98},
    ),
    (
        "线上支付服务宕机了，所有请求都失败，请立即处理！",
        {"category": CATEGORY_INCIDENT, "confidence": 0.99},
    ),
    (
        "我昨天提交的 INC-1024 工单处理到哪一步了？",
        {"category": CATEGORY_TICKET_INQUIRY, "confidence": 0.99},
    ),
    (
        "客服给的答复完全没解决问题，希望改进响应流程。",
        {"category": CATEGORY_COMPLAINT_SUGGESTION, "confidence": 0.97},
    ),
    (
        "公司年假一共有多少天，怎么申请？",
        {"category": CATEGORY_POLICY_GENERAL, "confidence": 0.98},
    ),
    (
        "什么是微服务架构，它和单体架构有什么区别？",
        {"category": CATEGORY_POLICY_GENERAL, "confidence": 0.94},
    ),
    (
        "今天天气怎么样？",
        {"category": CATEGORY_COMMON, "confidence": 0.98},
    ),
    (
        "git push 提示 Permission denied (publickey)，应该怎么排查？",
        {"category": CATEGORY_TECH, "confidence": 0.96},
    ),
    (
        "请给新同事开通 Git 仓库权限。",
        {"category": CATEGORY_ACCESS_REQUEST, "confidence": 0.98},
    ),
)

# ---------------------------------------------------------------------------
# 出参模型
# ---------------------------------------------------------------------------


class Classification(BaseModel):
    """T6 意图分类结果（对外契约）。"""

    category: str = Field(..., description=f"意图类别：{' / '.join(sorted(VALID_CATEGORIES))}")
    confidence: float = Field(..., ge=0.0, le=1.0, description="分类置信度，0~1")


# ---------------------------------------------------------------------------
# 对外接口
# ---------------------------------------------------------------------------


def classify(query: str) -> Classification:
    """对用户问题做七分类，供主链路路由。

    处理流程：
    1. 空 query 直接降级；
    2. 组装 few-shot Prompt 调用 LLM，要求仅输出 JSON；
    3. 解析并校验 LLM 返回（容忍 Markdown 代码块围栏与前后附加文字）；
    4. 置信度低于 LOW_CONFIDENCE_THRESHOLD 时按 tech 保守路由；
    5. LLM 失败 / 超时 / 返回格式非法时降级返回 tech 并记录日志，主链路不中断。

    Args:
        query: 用户问题。

    Returns:
        Classification: 分类结果（category、confidence）。
    """
    if not query or not query.strip():
        return _fallback("query 为空")

    messages = _build_few_shot_messages(query)

    try:
        raw = _call_llm(messages)
    except Exception as exc:  # 降级策略要求吞掉一切 LLM 异常，不向主链路抛出
        logger.error("intent.classify.llm_error query=%r error=%s", query, exc, exc_info=True)
        return _fallback(f"LLM 调用失败：{exc}")

    parsed = _parse_llm_json(raw)
    if parsed is None:
        logger.warning("intent.classify.invalid_format query=%r raw=%r", query, raw)
        return _fallback("LLM 返回格式非法")

    category, confidence = parsed

    if confidence < LOW_CONFIDENCE_THRESHOLD:
        logger.info(
            "intent.classify.low_confidence query=%r confidence=%.4f threshold=%.2f -> 保守路由为%s",
            query, confidence, LOW_CONFIDENCE_THRESHOLD, CATEGORY_TECH,
        )
        return Classification(category=CATEGORY_TECH, confidence=round(confidence, 4))

    logger.info("intent.classify.done query=%r category=%r confidence=%.4f", query, category, confidence)
    return Classification(category=category, confidence=round(confidence, 4))


# ---------------------------------------------------------------------------
# 内部实现
# ---------------------------------------------------------------------------

_llm_client: OpenAI | None = None
_llm_client_checked: bool = False
_llm_model: str = DEFAULT_MODEL

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def _build_few_shot_messages(query: str) -> list[dict[str, str]]:
    """组装 system + few-shot 对话对 + 当前 query 的消息列表。"""
    messages: list[dict[str, str]] = [{"role": "system", "content": SYSTEM_PROMPT}]
    for example_query, example_result in FEW_SHOT_EXAMPLES:
        messages.append({"role": "user", "content": example_query})
        messages.append({"role": "assistant", "content": json.dumps(example_result, ensure_ascii=False)})
    messages.append({"role": "user", "content": query})
    return messages


def _load_llm_settings() -> tuple[str, str, str]:
    """读取 LLM 接入配置，环境变量优先，其次 config.ini 的 [llm] 段。"""
    api_key = os.getenv("DASHSCOPE_API_KEY", "")
    base_url = os.getenv("DASHSCOPE_BASE_URL", DEFAULT_BASE_URL)
    model = os.getenv("LLM_MODEL", DEFAULT_MODEL)

    cfg = None
    if Config is not None:
        # 按文件位置定位项目根 config.ini，避免依赖运行 cwd
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        config_path = os.path.join(project_root, "config.ini")
        try:
            cfg = Config(config_file=config_path)
        except Exception:
            logger.warning("intent.classify.config_load_failed path=%s", config_path, exc_info=True)
    if cfg is not None:
        api_key = api_key or cfg.DASHSCOPE_API_KEY
        base_url = cfg.DASHSCOPE_BASE_URL or base_url
        model = cfg.LLM_MODEL or model
    return api_key, base_url, model


def _get_client() -> OpenAI | None:
    """懒加载 OpenAI 兼容客户端（进程内单例），不可用时返回 None。"""
    global _llm_client, _llm_client_checked, _llm_model
    if _llm_client_checked:
        return _llm_client
    _llm_client_checked = True

    api_key, base_url, model = _load_llm_settings()
    _llm_model = model
    if OpenAI is None:
        logger.error("intent.classify.no_openai_pkg: openai 包未安装，意图分类降级为 tech")
        return None
    if not api_key:
        logger.error("intent.classify.no_api_key: DASHSCOPE_API_KEY 未配置，意图分类降级为 tech")
        return None
    try:
        _llm_client = OpenAI(api_key=api_key, base_url=base_url, timeout=LLM_TIMEOUT_SECONDS)
    except Exception as exc:
        logger.error("intent.classify.init_client_failed error=%s", exc, exc_info=True)
        _llm_client = None
    return _llm_client


def _call_llm(messages: list[dict[str, str]]) -> str:
    """调用 LLM 完成分类，返回原始文本；失败 / 超时由调用方统一降级。"""
    client = _get_client()
    if client is None:
        raise RuntimeError("LLM 客户端不可用（api_key 缺失或 openai SDK 未安装）")
    resp = client.chat.completions.create(
        model=_llm_model,
        messages=messages,
        temperature=LLM_TEMPERATURE,
        max_tokens=LLM_MAX_TOKENS,
    )
    content = (resp.choices[0].message.content or "").strip() if resp.choices else ""
    if not content:
        raise RuntimeError("LLM 返回内容为空")
    return content


def _normalize_category(value: object) -> str | None:
    """校验类别，并兼容模型偶尔返回的中英文展示名称。"""
    if not isinstance(value, str):
        return None
    text = value.strip().lower()
    if not text:
        return None
    if text in VALID_CATEGORIES:
        return text
    aliases = {
        "技术咨询": CATEGORY_TECH,
        "权限/账号申请": CATEGORY_ACCESS_REQUEST,
        "权限申请": CATEGORY_ACCESS_REQUEST,
        "账号申请": CATEGORY_ACCESS_REQUEST,
        "故障上报": CATEGORY_INCIDENT,
        "工单/进度查询": CATEGORY_TICKET_INQUIRY,
        "工单查询": CATEGORY_TICKET_INQUIRY,
        "进度查询": CATEGORY_TICKET_INQUIRY,
        "投诉/建议": CATEGORY_COMPLAINT_SUGGESTION,
        "投诉建议": CATEGORY_COMPLAINT_SUGGESTION,
        "制度/通用知识": CATEGORY_POLICY_GENERAL,
        "制度通用知识": CATEGORY_POLICY_GENERAL,
        "通用知识": CATEGORY_POLICY_GENERAL,
        "闲聊": CATEGORY_COMMON,
    }
    return aliases.get(text)


def _parse_llm_json(raw: str) -> tuple[str, float] | None:
    """解析 LLM 返回的 JSON，容忍代码块围栏与前后附加文字；非法时返回 None。"""
    text = (raw or "").strip()
    if not text:
        return None

    fence = _FENCE_RE.search(text)
    if fence:
        text = fence.group(1).strip()

    # 容忍 JSON 前后附带的说明文字：截取首尾大括号之间的内容
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return None

    try:
        data = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None

    category = _normalize_category(data.get("category"))
    if category is None:
        return None

    try:
        confidence = float(data.get("confidence"))
    except (TypeError, ValueError):
        return None
    confidence = min(max(confidence, 0.0), 1.0)

    return category, confidence


def _fallback(reason: str) -> Classification:
    """降级结果：一律按 tech 保守路由，confidence=0 提示下游信息不足。"""
    full_reason = f"降级为 tech（{reason}）"
    logger.warning("intent.classify.fallback: %s", full_reason)
    return Classification(category=CATEGORY_TECH, confidence=0.0)


# ---------------------------------------------------------------------------
# 本地测试入口
# ---------------------------------------------------------------------------


def main() -> None:
    """T6 本地测试：对七类 query 及边界场景分类并与预期比对。

    运行方式（在项目根目录、激活 .venv 后）：
        python -m internal_kb_qa.core.intent_classifier
    或：
        python internal_kb_qa/core/intent_classifier.py

    需要已配置 DASHSCOPE_API_KEY（环境变量或 config.ini [llm] 段），否则全部走降级路径。
    """
    test_cases: list[tuple[str, str]] = [
        # tech：技术实操、普通报错和排查咨询
        ("打包部署到测试环境时页面 502，nginx 日志显示 upstream timed out，怎么排查？", CATEGORY_TECH),
        ("订单接口返回 401，调用时怎样正确携带 SSO token？", CATEGORY_TECH),
        # access_request：账号或权限的申请/开通
        ("请帮我开通 VPN 账号，我下周需要远程办公。", CATEGORY_ACCESS_REQUEST),
        ("需要申请 GitLab 项目的 Developer 权限。", CATEGORY_ACCESS_REQUEST),
        # incident：正在发生或已经发生的生产故障
        ("生产环境订单服务全挂了，当前用户都无法下单。", CATEGORY_INCIDENT),
        ("刚才发布失败并造成线上 P1 事故，请立即介入。", CATEGORY_INCIDENT),
        # ticket_inquiry：已有工单的状态、进度与催办
        ("工单 T20260823001 现在是谁在处理？", CATEGORY_TICKET_INQUIRY),
        ("上周提的权限工单还没完成，麻烦催一下进度。", CATEGORY_TICKET_INQUIRY),
        # complaint_suggestion：投诉、不满或改进建议
        ("这个问题反馈三次都没人处理，我要投诉。", CATEGORY_COMPLAINT_SUGGESTION),
        ("建议知识库增加搜索结果纠错功能。", CATEGORY_COMPLAINT_SUGGESTION),
        # policy_general：公司制度、福利和非技术概念知识
        ("出差住宿费的报销标准是多少？", CATEGORY_POLICY_GENERAL),
        ("什么是零信任安全模型？", CATEGORY_POLICY_GENERAL),
        # common：寒暄、天气及无关话题
        ("早上好，今天心情怎么样？", CATEGORY_COMMON),
        ("上海明天天气如何？", CATEGORY_COMMON),
        # 边界：空 query 预期降级为 tech
        ("", CATEGORY_TECH),
    ]

    total = len(test_cases)
    passed = 0
    for idx, (query, expected) in enumerate(test_cases, start=1):
        result = classify(query)
        ok = result.category == expected
        passed += 1 if ok else 0
        print(
            f"[{idx}/{total}] {'PASS' if ok else 'FAIL'} | 期望={expected} -> 实际={result.category} "
            f"(confidence={result.confidence:.4f})\n"
            f"    query={query!r}"
        )
    print(f"\n共 {total} 条测试，通过 {passed} 条，失败 {total - passed} 条")


if __name__ == "__main__":
    main()
