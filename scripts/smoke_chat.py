"""Quick smoke test for chat-related APIs."""
import json
import sys
import urllib.error
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8020"


def post(path: str, body: dict, token: str | None = None) -> dict:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers=headers,
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.load(resp)


def main() -> None:
    health = urllib.request.urlopen(f"{BASE}/health", timeout=10)
    print("health:", health.read().decode())

    login = post("/api/auth/login", {"account": "admin", "password": "123456"})
    token = login["access_token"]
    print("login: ok")

    faq = post("/api/faq/search", {"question": "生产环境如何配置统一身份认证？"}, token)
    print("faq:", "found=", faq.get("found"), "answer_len=", len(faq.get("answer") or ""))

    for label, question in [("EN", "Milvus"), ("CN", "向量数据库")]:
        ret = post(
            "/api/knowledge/retrieval/search",
            {"question": question, "top_k": 5, "use_rerank": False, "use_llm_rewrite": False},
            token,
        )
        print(f"retrieval {label}:", "items=", len(ret.get("items") or []), "warning=", ret.get("warning"))


if __name__ == "__main__":
    try:
        main()
    except urllib.error.HTTPError as exc:
        print("HTTP", exc.code, exc.read().decode())
        sys.exit(1)
