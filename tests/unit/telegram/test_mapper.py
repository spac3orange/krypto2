"""Unit tests for Telethon → DTO mapper."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from app.core.errors import MappingError
from app.domain.telegram.enums import TelegramEventType
from app.infrastructure.telegram.mapper import to_message_event


def test_map_new_message(fake_telethon_message: SimpleNamespace) -> None:
    event = to_message_event(
        fake_telethon_message,
        event_type=TelegramEventType.NEW_MESSAGE,
        expected_chat_id=-100123,
        received_at=datetime(2026, 1, 1, 12, 0, 5, tzinfo=UTC),
    )
    assert event.event_type is TelegramEventType.NEW_MESSAGE
    assert event.event_id == "telegram:-100123:42:new"
    assert event.chat_id == -100123
    assert event.message_id == 42
    assert event.sender_id == 7
    assert event.sender_username == "signal_bot"
    assert event.chat_username == "signals"
    assert event.text == "LONG BTCUSDT"
    assert event.date.tzinfo is not None
    assert event.date == datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    assert event.edit_date is None
    assert event.has_media is False
    assert event.reply_to_message_id is None


def test_map_edited_message(fake_telethon_message: SimpleNamespace) -> None:
    edit_date = datetime(2026, 1, 1, 12, 15, tzinfo=UTC)
    fake_telethon_message.edit_date = edit_date
    fake_telethon_message.message = "LONG BTCUSDT SL updated"

    event = to_message_event(
        fake_telethon_message,
        event_type=TelegramEventType.MESSAGE_EDITED,
        expected_chat_id=-100123,
    )
    assert event.event_type is TelegramEventType.MESSAGE_EDITED
    assert event.event_id == f"telegram:-100123:42:edited:{int(edit_date.timestamp())}"
    assert event.edit_date == edit_date


def test_map_naive_datetime_becomes_utc(fake_telethon_message: SimpleNamespace) -> None:
    fake_telethon_message.date = datetime(2026, 1, 1, 12, 0)
    event = to_message_event(
        fake_telethon_message,
        event_type=TelegramEventType.NEW_MESSAGE,
    )
    assert event.date.tzinfo is not None
    assert event.date == datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def test_map_empty_text(fake_telethon_message: SimpleNamespace) -> None:
    fake_telethon_message.message = None
    fake_telethon_message.text = None
    event = to_message_event(
        fake_telethon_message,
        event_type=TelegramEventType.NEW_MESSAGE,
    )
    assert event.text == ""
    assert event.event_id.endswith(":new")


def test_map_media_message(fake_telethon_message: SimpleNamespace) -> None:
    fake_telethon_message.media = object()
    fake_telethon_message.message = ""
    event = to_message_event(
        fake_telethon_message,
        event_type=TelegramEventType.NEW_MESSAGE,
    )
    assert event.has_media is True


def test_map_reply_message(fake_telethon_message: SimpleNamespace) -> None:
    fake_telethon_message.reply_to = SimpleNamespace(reply_to_msg_id=10)
    event = to_message_event(
        fake_telethon_message,
        event_type=TelegramEventType.NEW_MESSAGE,
    )
    assert event.reply_to_message_id == 10


def test_map_rejects_wrong_chat(fake_telethon_message: SimpleNamespace) -> None:
    with pytest.raises(MappingError):
        to_message_event(
            fake_telethon_message,
            event_type=TelegramEventType.NEW_MESSAGE,
            expected_chat_id=999,
        )


def test_map_missing_id_raises(fake_telethon_message: SimpleNamespace) -> None:
    fake_telethon_message.id = None
    with pytest.raises(MappingError):
        to_message_event(
            fake_telethon_message,
            event_type=TelegramEventType.NEW_MESSAGE,
        )
