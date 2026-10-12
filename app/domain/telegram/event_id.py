"""Stable event ID generation for Telegram events."""

from __future__ import annotations

from datetime import datetime

from app.domain.telegram.enums import TelegramEventType


def build_event_id(
    *,
    chat_id: int,
    message_id: int,
    event_type: TelegramEventType,
    edit_date: datetime | None = None,
    fallback_edit_ts: int | None = None,
) -> str:
    """Build a stable idempotency key for a Telegram message event.

    Schemes:
    - new: ``telegram:{chat_id}:{message_id}:new``
    - edited: ``telegram:{chat_id}:{message_id}:edited:{edit_unix_ts}``
    """
    if event_type is TelegramEventType.NEW_MESSAGE:
        return f"telegram:{chat_id}:{message_id}:new"

    if event_type is TelegramEventType.MESSAGE_EDITED:
        if edit_date is not None:
            ts = int(edit_date.timestamp())
        elif fallback_edit_ts is not None:
            ts = fallback_edit_ts
        else:
            ts = 0
        return f"telegram:{chat_id}:{message_id}:edited:{ts}"

    msg = f"Unsupported event type: {event_type}"
    raise ValueError(msg)
