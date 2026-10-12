"""Operator bot uses PROXY_URL (no network)."""

from __future__ import annotations

import pytest
from app.infrastructure.bot.service import create_operator_bot


@pytest.mark.asyncio
async def test_operator_bot_session_uses_proxy() -> None:
    bot = create_operator_bot("1:token", "http://user:pass@1.2.3.4:8000")
    assert bot.session.proxy == "http://user:pass@1.2.3.4:8000"
    await bot.session.close()


@pytest.mark.asyncio
async def test_operator_bot_without_proxy() -> None:
    bot = create_operator_bot("1:token", None)
    assert bot.session.proxy is None
    await bot.session.close()
