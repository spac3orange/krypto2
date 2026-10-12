"""Internal Telegram message event DTO."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.domain.telegram.enums import TelegramEventType


@dataclass(frozen=True, slots=True)
class TelegramMessageEvent:
    """Normalized Telegram message event (Telethon-free)."""

    event_id: str
    event_type: TelegramEventType
    chat_id: int
    message_id: int
    sender_id: int | None
    sender_username: str | None
    chat_username: str | None
    text: str
    date: datetime
    edit_date: datetime | None
    received_at: datetime
    has_media: bool
    reply_to_message_id: int | None
