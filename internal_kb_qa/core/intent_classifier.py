"""T6 意图分类与路由。

对外接口：
    classify(query: str) -> Classification

类别（两类，与基线 QueryClassifier 对齐）：
    - 通用知识：闲聊/常识问题，直接 LLM 回答，不检索知识库
    - 专业咨询：技术问题，走 FAQ 精确匹配 -> RAG 主链路

低置信度按专业咨询保守路由（宁可不答，不错答）。
参考：rag_qa/core/bert_query_classifier/ 与 query_classifier.py
"""
# TODO(T6 算法组): 微调 BERT；低置信度按专业咨询保守路由。
