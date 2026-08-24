# -*- coding: utf-8 -*-
"""用户短信登录单元测试。"""
import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from backend.app.services import user_service


def test_login_by_sms_auto_registers_new_phone():
    async def run():
        with patch("backend.app.services.user_service.verify_sms_code", new=AsyncMock()), patch(
            "backend.app.services.user_service.db.fetch_one",
            new=AsyncMock(
                side_effect=[
                    None,
                    {
                        "id": 9,
                        "username": "u13800000001",
                        "nickname": "用户0001",
                        "phone": "13800000001",
                        "team": "default",
                        "security_level": "team",
                        "is_active": 1,
                    },
                ]
            ),
        ), patch("backend.app.services.user_service.db.execute_lastrowid", new=AsyncMock(return_value=9)), patch(
            "backend.app.services.user_service.asyncio.to_thread", new=AsyncMock(return_value="hash")
        ):
            return await user_service.login_by_sms("13800000001", "123456")

    user = asyncio.run(run())
    assert user["phone"] == "13800000001"
    assert user["username"] == "u13800000001"


def test_send_sms_code_rolls_back_rate_limit_on_provider_failure():
    async def run():
        with patch("backend.app.services.user_service.db.redis_sms") as mock_redis, patch(
            "backend.app.services.user_service.sms_service.send_verification_code",
            new=AsyncMock(side_effect=RuntimeError("provider down")),
        ):
            mock_redis.set = AsyncMock(return_value=True)
            mock_redis.delete = AsyncMock()
            with pytest.raises(RuntimeError):
                await user_service.send_sms_code("13800000000")
            mock_redis.delete.assert_awaited()

    asyncio.run(run())

