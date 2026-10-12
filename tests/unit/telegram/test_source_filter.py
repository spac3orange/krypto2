"""Unit tests for source chat filtering in handlers/mapper path."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from app.application.telegram.deduplicator import InMemoryEventDeduplicator
from app.domain.telegram.models import TelegramMessageEvent
from app.infrastructure.telegram.handlers import TelegramEventHandlers


class RecordingProcessor:
    def __init__(self) -> None:
        self.events: list[TelegramMessageEvent] = []

    async def process(self, event: TelegramMessageEvent) -> None:
        self.events.append(event)


@pytest.mark.asyncio
async def test_handler_drops_mismatched_source_without_killing_loop() -> None:
    processor = RecordingProcessor()
    handlers = TelegramEventHandlers(
        processor=processor,
        deduplicator=InMemoryEventDeduplicator(),
        expected_chat_id=-100123,
    )
    event = SimpleNamespace(
        message=SimpleNamespace(
            id=1,
            chat_id=999,
            sender_id=1,
            message="x",
            text="x",
            date=datetime(2026, 1, 1, tzinfo=UTC),
            edit_date=None,
            media=None,
            reply_to=None,
            chat=None,
            sender=None,
        )
    )
    await handlers.handle_new_message(event)
    assert processor.events == []


@pytest.mark.asyncio
async def test_handler_processes_matching_source() -> None:
    processor = RecordingProcessor()
    handlers = TelegramEventHandlers(
        processor=processor,
        deduplicator=InMemoryEventDeduplicator(),
        expected_chat_id=-100123,
    )
    event = SimpleNamespace(
        message=SimpleNamespace(
            id=7,
            chat_id=-100123,
            sender_id=1,
            message="signal",
            text="signal",
            date=datetime(2026, 1, 1, tzinfo=UTC),
            edit_date=None,
            media=None,
            reply_to=None,
            chat=SimpleNamespace(username="ch"),
            sender=SimpleNamespace(username="bot"),
        )
    )
    await handlers.handle_new_message(event)
    assert len(processor.events) == 1
    assert processor.events[0].message_id == 7


@pytest.mark.asyncio
async def test_handler_suppresses_duplicates() -> None:
    processor = RecordingProcessor()
    handlers = TelegramEventHandlers(
        processor=processor,
        deduplicator=InMemoryEventDeduplicator(),
        expected_chat_id=-100123,
    )
    message = SimpleNamespace(
        id=7,
        chat_id=-100123,
        sender_id=1,
        message="signal",
        text="signal",
        date=datetime(2026, 1, 1, tzinfo=UTC),
        edit_date=None,
        media=None,
        reply_to=None,
        chat=None,
        sender=None,
    )
    event = SimpleNamespace(message=message)
    await handlers.handle_new_message(event)
    await handlers.handle_new_message(event)
    assert len(processor.events) == 1
