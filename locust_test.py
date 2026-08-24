"""T11 压测脚本：Locust 性能测试。

参考基线：E:/study_project/Itcast_qa_system/locust_test.py
验收口径：50 并发 p95 延迟 < 5 秒（健康检查 / FAQ 检索）。

用法：
    locust -f locust_test.py --host http://127.0.0.1:8004
"""
import os

from locust import HttpUser, between, task


class QaUser(HttpUser):
    wait_time = between(0.5, 2)
    token = None

    def on_start(self):
        account = os.getenv("LOCUST_ACCOUNT", "admin")
        password = os.getenv("LOCUST_PASSWORD", "123456")
        with self.client.post(
            "/api/auth/login",
            json={"account": account, "password": password},
            catch_response=True,
        ) as response:
            if response.status_code != 200:
                response.failure(f"login failed: {response.status_code}")
                return
            data = response.json()
            self.token = data.get("access_token")

    def _auth_headers(self):
        if not self.token:
            return {}
        return {"Authorization": f"Bearer {self.token}"}

    @task(3)
    def health(self):
        self.client.get("/health")

    @task(5)
    def faq_search(self):
        self.client.post(
            "/api/faq/search",
            json={"question": "生产环境如何配置统一身份认证？"},
            headers=self._auth_headers(),
        )

    @task(2)
    def retrieval_search(self):
        self.client.post(
            "/api/knowledge/retrieval/search",
            json={
                "question": "Milvus 向量库",
                "top_k": 5,
                "mode": "hybrid",
                "use_rerank": False,
                "use_llm_rewrite": False,
            },
            headers=self._auth_headers(),
        )
