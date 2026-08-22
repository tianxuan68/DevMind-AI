"""T13 检索策略路由。

对外接口：
    build_search_strategy(query: str, category: str) -> SearchStrategy
策略：faq / hybrid / runbook / none
"""
# TODO(T13 算法组): tech->hybrid, access_request->权限过滤, incident->runbook优先, chitchat->none。
