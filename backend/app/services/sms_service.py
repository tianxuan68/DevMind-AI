"""Spug 推送助手消息模板短信验证码。

文档：https://push.spug.cc/guide/push/var
POST https://push.spug.cc/send/<TEMPLATE_CODE>
Body: code、number、targets（手机号）

使用示例（勿随意真实发送）::

    from backend.app.services.sms_service import send_verification_code

    # await send_verification_code("13800000000", "123456")
"""
import asyncio
import json
import logging
import urllib.error
import urllib.parse
import urllib.request

from fastapi import HTTPException

from backend.app.core.config import settings

logger = logging.getLogger("devmind.sms")


def _mask_phone(phone: str) -> str:
    if len(phone) < 7:
        return "***"
    return f"{phone[:3]}****{phone[-4:]}"


def _build_headers(content_type: str) -> dict[str, str]:
    headers = {
        "Content-Type": content_type,
        "User-Agent": "DevMind-AI/1.0",
    }
    if settings.SPUG_SMS_APP_KEY:
        headers["X-App-Key"] = settings.SPUG_SMS_APP_KEY
    if settings.SPUG_SMS_CREDENTIAL:
        headers["Authorization"] = f"Bearer {settings.SPUG_SMS_CREDENTIAL}"
    return headers


def _parse_response(raw: str) -> dict:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=502, detail="短信服务响应格式异常") from exc
    if not isinstance(data, dict):
        raise HTTPException(status_code=502, detail="短信服务响应格式异常")
    return data


def _is_success(data: dict) -> bool:
    code = data.get("code")
    return code in {0, 200}


def _send_via_spug_sync(phone: str, code: str) -> dict:
    """POST 消息模板 send 接口发送验证码。"""
    url = settings.SPUG_SMS_SEND_URL or f"https://push.spug.cc/send/{settings.SPUG_SMS_TEMPLATE}"
    form_body = {
        "code": code,
        "number": str(settings.SPUG_SMS_NUMBER),
        "targets": phone,
    }
    if settings.SPUG_SMS_APP_NAME:
        form_body["name"] = settings.SPUG_SMS_APP_NAME

    # Spug 官方 curl 示例使用 form 表单
    payload = urllib.parse.urlencode(form_body).encode("utf-8")
    headers = _build_headers("application/x-www-form-urlencoded")
    request = urllib.request.Request(url, data=payload, headers=headers, method="POST")

    logger.info(
        "Spug send request url=%s phone=%s",
        url,
        _mask_phone(phone),
    )

    try:
        with urllib.request.urlopen(request, timeout=settings.SPUG_SMS_TIMEOUT) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        logger.error("Spug SMS HTTP error phone=%s status=%s body=%s", _mask_phone(phone), exc.code, detail)
        try:
            err_data = json.loads(detail)
            msg = err_data.get("msg") or err_data.get("message")
            if msg:
                raise HTTPException(status_code=502, detail=msg) from exc
        except json.JSONDecodeError:
            pass
        raise HTTPException(status_code=502, detail="验证码发送失败，请稍后重试") from exc
    except urllib.error.URLError as exc:
        logger.error("Spug SMS network error phone=%s err=%s", _mask_phone(phone), exc)
        raise HTTPException(status_code=502, detail="验证码发送失败，请稍后重试") from exc

    data = _parse_response(body)
    if not _is_success(data):
        logger.error("Spug SMS rejected phone=%s response=%s", _mask_phone(phone), data)
        msg = data.get("msg") or data.get("message") or "验证码发送失败"
        raise HTTPException(status_code=502, detail=msg)

    logger.info(
        "Spug SMS accepted phone=%s request_id=%s",
        _mask_phone(phone),
        data.get("request_id") or data.get("data"),
    )
    return data


async def send_verification_code(phone: str, code: str) -> None:
    """向手机号发送验证码。"""
    if not settings.SPUG_SMS_ENABLED:
        logger.info("SMS disabled, skip external send phone=%s", _mask_phone(phone))
        return
    await asyncio.to_thread(_send_via_spug_sync, phone, code)
