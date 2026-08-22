"""T6 意图分类与路由。

对外接口：
    classify(query: str) -> Classification
类别：tech / access_request / incident / complaint / chitchat
参考：rag_qa/core/bert_query_classifier/ 与 query_classifier.py
"""
# TODO(T6 算法组): 微调 BERT；低置信度按 tech 保守路由。
