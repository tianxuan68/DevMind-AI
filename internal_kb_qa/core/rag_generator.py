"""T7 重排 + DashScope 流式生成回答。

对外接口：
    rag_answer(query: str, history: list = None) -> RAGResult
要求：仅依据检索文档回答 + 标注出处 + 不知道时明确说不知道。
"""
# TODO(T7 算法组): 流式首 token < 1.5s；低置信度触发转人工。
