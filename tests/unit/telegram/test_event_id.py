"""Unit tests for event_id generation."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from app.domain.telegram.enums import TelegramEventType
from app.domain.telegram.event_id import build_event_id


def test_new_message_event_id() -> None:
    event_id = build_event_id(
        chat_id=-100123,
        message_id=42,
        event_type=TelegramEventType.NEW_MESSAGE,
    )
    assert event_id == "telegram:-100123:42:new"


def test_edited_message_event_id_uses_edit_timestamp() -> None:
    edit_date = datetime(2026, 1, 1, 12, 30, tzinfo=UTC)
    event_id = build_event_id(
        chat_id=-100123,
        message_id=42,
        event_type=TelegramEventType.MESSAGE_EDITED,
        edit_date=edit_date,
    )
    assert event_id == f"telegram:-100123:42:edited:{int(edit_date.timestamp())}"


def test_edited_message_falls_back_to_provided_ts() -> None:
    event_id = build_event_id(
        chat_id=1,
        message_id=2,
        event_type=TelegramEventType.MESSAGE_EDITED,
        edit_date=None,
        fallback_edit_ts=99,
    )
    assert event_id == "telegram:1:2:edited:99"


def test_unsupported_event_type_raises() -> None:
    with pytest.raises(ValueError):
        build_event_id(
            chat_id=1,
            message_id=2,
            event_type="deleted",  # type: ignore[arg-type]
        )
