"""WS /api/stream（流式 RAG 主链路）。

消息时序（契约见 docs/api/接口文档.md）：
1. 客户端先发 {"type": "auth", "token": "<sso token>"}，认证失败即关闭；
2. 服务端回 {"type": "start", "session_id"}；
3. 客户端发 {"type": "query", "query", "session_id", "source_filter"}；
4. 服务端逐条下发 {"type": "token", "token"}，结束发
   {"type": "end", "is_complete", "sources", "processing_time"}；
   异常发 {"type": "error", "error"}。

MVP 取舍：query_events 为同步生成器（LLM 调用阻塞事件循环），
与基线实现一致；后续可切换异步 LLM 客户端或 SSE。
"""
import json
import logging
import time
import uuid

from fastapi import APIRouter, WebSocket
from starlette.websockets import WebSocketDisconnect

from internal_kb_qa.api.deps import SSOAuth, SSOAuthError

logger = logging.getLogger("internal_kb_qa.api.routers.stream")

router = APIRouter()

_sso = SSOAuth()


@router.websocket("/api/stream")
async def stream(websocket: WebSocket):
    await websocket.accept()
    qa_system = websocket.app.state.qa_system

    # 1. SSO 认证（首条消息必须为 auth）
    user = None
    try:
        first = json.loads(await websocket.receive_text())
        if first.get("type") != "auth" or not first.get("token"):
            await websocket.send_json({"type": "error", "error": "未认证或 token 无效"})
            await websocket.close()
            return
        user = _sso.authenticate(first["token"])
    except SSOAuthError as e:
        logger.warning("WS 认证失败: %s", e)
        await websocket.send_json({"type": "error", "error": f"未认证或 token 无效: {e}"})
        await websocket.close()
        return
    except (json.JSONDecodeError, WebSocketDisconnect):
        return

    # 2. 认证通过，立即下发 start（携带会话 ID，契约时序）
    session_id = str(uuid.uuid4())
    await websocket.send_json({"type": "start", "session_id": session_id})

    # 3. 循环处理查询消息
    try:
        while True:
            data = json.loads(await websocket.receive_text())
            if data.get("type") != "query":
                await websocket.send_json({"type": "error", "error": "未知消息类型"})
                continue
            query = data.get("query", "").strip()
            if not query:
                await websocket.send_json({"type": "error", "error": "query 不能为空"})
                continue
            session_id = data.get("session_id") or session_id
            source_filter = data.get("source_filter")
            start_time = time.time()
            try:
                for event in qa_system.query_events(query, session_id, source_filter, user):
                    if event["type"] == "token":
                        await websocket.send_json({"type": "token", "token": event["token"]})
                    else:  # end
                        await websocket.send_json({
                            "type": "end",
                            "is_complete": event.get("is_complete", True),
                            "sources": event.get("sources") or [],
                            "need_human": bool(event.get("need_human")),
                            "processing_time": round(time.time() - start_time, 3),
                        })
            except Exception as e:
                logger.error("流式查询失败: %s", e)
                await websocket.send_json({"type": "error", "error": str(e)})
    except WebSocketDisconnect:
        logger.info("WebSocket 连接断开")
    except Exception as e:
        logger.error("WebSocket 错误: %s", e)
        try:
            await websocket.send_json({"type": "error", "error": str(e)})
        except Exception:
            pass
