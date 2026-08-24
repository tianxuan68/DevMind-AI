# -*- coding: utf-8 -*-
"""短信服务单元测试。"""
import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from backend.app.services import sms_service


class TestSmsService:
    def test_is_success_accepts_200_and_0(self):
        assert sms_service._is_success({"code": 200}) is True
        assert sms_service._is_success({"code": 0}) is True
        assert sms_service._is_success({"code": 404}) is False

    def test_send_via_spug_sync_post_success(self):
        response = MagicMock()
        response.read.return_value = json.dumps({"code": 200, "request_id": "req-1"}).encode()
        response.__enter__ = MagicMock(return_value=response)
        response.__exit__ = MagicMock(return_value=False)

        with patch("backend.app.services.sms_service.settings") as mock_settings, patch(
            "urllib.request.urlopen", return_value=response
        ) as mock_open:
            mock_settings.SPUG_SMS_SEND_URL = "https://push.spug.cc/send/test"
            mock_settings.SPUG_SMS_TEMPLATE = "test"
            mock_settings.SPUG_SMS_APP_NAME = "DevMind AI"
            mock_settings.SPUG_SMS_NUMBER = "10"
            mock_settings.SPUG_SMS_APP_KEY = ""
            mock_settings.SPUG_SMS_CREDENTIAL = ""
            mock_settings.SPUG_SMS_TIMEOUT = 10

            data = sms_service._send_via_spug_sync("13800000000", "123456")
            assert data["request_id"] == "req-1"
            request = mock_open.call_args[0][0]
            assert request.method == "POST"
            assert request.full_url == "https://push.spug.cc/send/test"
            assert "code=123456" in request.data.decode()
            assert "targets=13800000000" in request.data.decode()
            assert "number=10" in request.data.decode()

    def test_send_via_spug_sync_rejects_failure(self):
        response = MagicMock()
        response.read.return_value = json.dumps(
            {"code": 404, "msg": "该编码属于消息模板，请使用 send 接口"}
        ).encode()
        response.__enter__ = MagicMock(return_value=response)
        response.__exit__ = MagicMock(return_value=False)

        with patch("backend.app.services.sms_service.settings") as mock_settings, patch(
            "urllib.request.urlopen", return_value=response
        ):
            mock_settings.SPUG_SMS_SEND_URL = "https://push.spug.cc/send/test"
            mock_settings.SPUG_SMS_TEMPLATE = "test"
            mock_settings.SPUG_SMS_APP_NAME = ""
            mock_settings.SPUG_SMS_NUMBER = "10"
            mock_settings.SPUG_SMS_APP_KEY = ""
            mock_settings.SPUG_SMS_CREDENTIAL = ""
            mock_settings.SPUG_SMS_TIMEOUT = 10

            with pytest.raises(HTTPException) as exc:
                sms_service._send_via_spug_sync("13800000000", "123456")
            assert exc.value.status_code == 502

    def test_send_verification_code_skips_when_disabled(self):
        async def run():
            with patch("backend.app.services.sms_service.settings") as mock_settings, patch(
                "backend.app.services.sms_service.asyncio.to_thread"
            ) as mock_thread:
                mock_settings.SPUG_SMS_ENABLED = False
                await sms_service.send_verification_code("13800000000", "123456")
                mock_thread.assert_not_called()

        import asyncio

        asyncio.run(run())
