"""Shared pytest fixtures."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from app.domain.telegram.enums import TelegramEventType
from app.domain.telegram.models import TelegramMessageEvent


@pytest.fixture
def sample_new_event() -> TelegramMessageEvent:
    return TelegramMessageEvent(
        event_id="telegram:-100123:42:new",
        event_type=TelegramEventType.NEW_MESSAGE,
        chat_id=-100123,
        message_id=42,
        sender_id=7,
        sender_username="signal_bot",
        chat_username="signals",
        text="LONG BTCUSDT",
        date=datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
        edit_date=None,
        received_at=datetime(2026, 1, 1, 12, 0, 1, tzinfo=UTC),
        has_media=False,
        reply_to_message_id=None,
    )


@pytest.fixture
def fake_telethon_message() -> SimpleNamespace:
    return SimpleNamespace(
        id=42,
        chat_id=-100123,
        sender_id=7,
        message="LONG BTCUSDT",
        text="LONG BTCUSDT",
        date=datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
        edit_date=None,
        media=None,
        reply_to=None,
        reply_to_msg_id=None,
        chat=SimpleNamespace(username="signals"),
        sender=SimpleNamespace(username="signal_bot"),
    )
