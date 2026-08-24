"""T7 重排 + DashScope 流式生成回答。

对外接口（与 T8 编排层对齐）：
    rag_answer(query, history, category, filter=None) -> RAGResult
    rag_answer_stream(query, history, category, filter=None) -> Generator[dict]

参数说明：
    - category：T6 意图类别（通用知识 / 专业咨询），用于检索策略路由（T13）；
      通用知识问题不走本模块（T8 直接模板/LLM 回答）。
    - filter：T8 注入的权限过滤条件 {team, security_level}，**必须接受并在
      检索链路强制使用**（R9 硬指标：越权命中数必须为 0），透传给 T4 search。

RAGResult 字段：answer（生成答案，含"不知道"的诚实兜底）、sources（引用出处，
元素 {title, page, score, text}）、confidence（综合置信度，供转人工判断）。

rag_answer_stream 产出事件：
    {"type": "token", "token": "..."}        流式文本片段，可多次
    {"type": "end", "sources": [...], "confidence": 0.9}   结束，附引用与置信度

要求：仅依据检索文档回答 + 标注出处 + 不知道时明确说不知道；
流式首 token < 1.5s；低置信度触发转人工（由 T8 编排层判断）。
"""
# TODO(T7 算法组): 流式首 token < 1.5s；低置信度触发转人工。
