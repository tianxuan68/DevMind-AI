"""T6 意图分类与路由。

对外接口：
    classify(query: str) -> Classification

类别（七类）：
    - tech：技术咨询（环境配置、常见报错等），走 FAQ -> RAG 主链路
    - access_request：权限/账号申请，引导审批流程
    - incident：故障上报，不硬答，转人工建单
    - ticket_inquiry：工单/进度查询，返回用户最近工单状态
    - complaint_suggestion：投诉/建议；投诉转人工建单，建议致谢
    - policy_general：制度类问题（制度/规范/报销/考勤等），走 FAQ -> RAG
    - chitchat（= common）：闲聊，模板直答不检索

低置信度按 tech 保守路由（宁可不答，不错答）。
参考：rag_qa/core/bert_query_classifier/ 与 query_classifier.py
"""
# TODO(T6 算法组): 微调 BERT；低置信度按 tech 保守路由。
