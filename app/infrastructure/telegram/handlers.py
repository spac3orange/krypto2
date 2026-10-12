"""Thin Telethon event handlers."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from app.core.errors import MappingError, ProcessingError
from app.core.logging import log_event
from app.domain.telegram.enums import TelegramEventType
from app.domain.telegram.models import TelegramMessageEvent
from app.domain.telegram.ports import EventDeduplicator, MessageProcessor
from app.infrastructure.telegram.mapper import to_message_event

logger = logging.getLogger(__name__)

MessageHandler = Callable[[Any], Awaitable[None]]


class TelegramEventHandlers:
    """Registers and processes NewMessage / MessageEdited events."""

    def __init__(
        self,
        *,
        processor: MessageProcessor,
        deduplicator: EventDeduplicator,
        expected_chat_id: int,
    ) -> None:
        self._processor = processor
        self._deduplicator = deduplicator
        self._expected_chat_id = expected_chat_id

    async def handle_new_message(self, event: Any) -> None:
        await self._handle(event, TelegramEventType.NEW_MESSAGE)

    async def handle_message_edited(self, event: Any) -> None:
        await self._handle(event, TelegramEventType.MESSAGE_EDITED)

    async def _handle(self, event: Any, event_type: TelegramEventType) -> None:
        try:
            message = getattr(event, "message", event)
            dto = to_message_event(
                message,
                event_type=event_type,
                expected_chat_id=self._expected_chat_id,
            )
            if self._deduplicator.seen(dto.event_id):
                log_event(
                    logger,
                    logging.DEBUG,
                    "telegram.message.duplicate",
                    "Duplicate Telegram event suppressed",
                    event_id=dto.event_id,
                    chat_id=dto.chat_id,
                    message_id=dto.message_id,
                    event_type=dto.event_type.value,
                )
                return
            await self._dispatch(dto)
        except MappingError as exc:
            log_event(
                logger,
                logging.ERROR,
                "telegram.message.processing_failed",
                "Failed to map Telegram event",
                error_type=type(exc).__name__,
                error=str(exc),
                event_type=event_type.value,
            )
        except Exception as exc:
            log_event(
                logger,
                logging.ERROR,
                "telegram.message.processing_failed",
                "Unexpected error while handling Telegram event",
                error_type=type(exc).__name__,
                error=str(exc),
                event_type=event_type.value,
            )

    async def _dispatch(self, dto: TelegramMessageEvent) -> None:
        try:
            await self._processor.process(dto)
        except Exception as exc:
            raise ProcessingError("Message processor failed") from exc
