"""Map Telethon events to internal TelegramMessageEvent DTOs."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.core.errors import MappingError
from app.domain.telegram.enums import TelegramEventType
from app.domain.telegram.event_id import build_event_id
from app.domain.telegram.models import TelegramMessageEvent


def _ensure_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _chat_id_from_message(message: Any) -> int:
    chat_id = getattr(message, "chat_id", None)
    if chat_id is not None:
        return int(chat_id)
    peer_id = getattr(message, "peer_id", None)
    if peer_id is not None:
        channel_id = getattr(peer_id, "channel_id", None)
        if channel_id is not None:
            return int(f"-100{channel_id}")
        chat_peer = getattr(peer_id, "chat_id", None)
        if chat_peer is not None:
            return -int(chat_peer)
        user_id = getattr(peer_id, "user_id", None)
        if user_id is not None:
            return int(user_id)
    msg = "Unable to resolve chat_id from Telegram message"
    raise MappingError(msg)


def _sender_id(message: Any) -> int | None:
    sender_id = getattr(message, "sender_id", None)
    if sender_id is not None:
        return int(sender_id)
    from_id = getattr(message, "from_id", None)
    if from_id is not None and getattr(from_id, "user_id", None) is not None:
        return int(from_id.user_id)
    return None


def _username(entity: Any | None) -> str | None:
    if entity is None:
        return None
    username = getattr(entity, "username", None)
    return str(username) if username else None


def _reply_to_message_id(message: Any) -> int | None:
    reply_to = getattr(message, "reply_to", None)
    if reply_to is None:
        # Telethon custom Message exposes reply_to_msg_id
        value = getattr(message, "reply_to_msg_id", None)
        return int(value) if value is not None else None
    msg_id = getattr(reply_to, "reply_to_msg_id", None)
    return int(msg_id) if msg_id is not None else None


def _has_media(message: Any) -> bool:
    media = getattr(message, "media", None)
    return media is not None


def _text(message: Any) -> str:
    text = getattr(message, "message", None)
    if text is None:
        text = getattr(message, "text", None)
    if text is None:
        return ""
    return str(text)


def to_message_event(
    message: Any,
    *,
    event_type: TelegramEventType,
    expected_chat_id: int | None = None,
    received_at: datetime | None = None,
) -> TelegramMessageEvent:
    """Convert a Telethon message-like object into TelegramMessageEvent."""
    try:
        chat_id = _chat_id_from_message(message)
        if expected_chat_id is not None and chat_id != expected_chat_id:
            msg = f"Message chat_id {chat_id} does not match source {expected_chat_id}"
            raise MappingError(msg)

        message_id = getattr(message, "id", None)
        if message_id is None:
            msg = "Telegram message is missing id"
            raise MappingError(msg)

        raw_date = getattr(message, "date", None)
        date = _ensure_utc(raw_date)
        if date is None:
            msg = "Telegram message is missing date"
            raise MappingError(msg)

        edit_date = _ensure_utc(getattr(message, "edit_date", None))
        now = received_at or datetime.now(UTC)
        now = _ensure_utc(now) or datetime.now(UTC)

        chat = getattr(message, "chat", None)
        sender = getattr(message, "sender", None)

        event_id = build_event_id(
            chat_id=chat_id,
            message_id=int(message_id),
            event_type=event_type,
            edit_date=edit_date,
            fallback_edit_ts=int(now.timestamp())
            if event_type is TelegramEventType.MESSAGE_EDITED and edit_date is None
            else None,
        )

        return TelegramMessageEvent(
            event_id=event_id,
            event_type=event_type,
            chat_id=chat_id,
            message_id=int(message_id),
            sender_id=_sender_id(message),
            sender_username=_username(sender),
            chat_username=_username(chat),
            text=_text(message),
            date=date,
            edit_date=edit_date,
            received_at=now,
            has_media=_has_media(message),
            reply_to_message_id=_reply_to_message_id(message),
        )
    except MappingError:
        raise
    except Exception as exc:
        raise MappingError("Failed to map Telegram message") from exc
