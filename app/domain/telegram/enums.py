"""Telegram domain enums."""

from __future__ import annotations

from enum import StrEnum


class TelegramEventType(StrEnum):
    """Internal Telegram event kinds."""

    NEW_MESSAGE = "new_message"
    MESSAGE_EDITED = "message_edited"
