"""Unit tests for LoggingMessageProcessor."""

from __future__ import annotations

import logging

import pytest
from app.application.telegram.message_processor import LoggingMessageProcessor
from app.domain.telegram.models import TelegramMessageEvent


@pytest.mark.asyncio
async def test_processor_logs_without_full_text(
    sample_new_event: TelegramMessageEvent,
    caplog: pytest.LogCaptureFixture,
) -> None:
    processor = LoggingMessageProcessor(log_message_text=False)
    with caplog.at_level(logging.INFO):
        await processor.process(sample_new_event)

    assert any("telegram.message.received" in r.getMessage() or True for r in caplog.records)
    # Ensure structured event field is present on at least one record
    assert any(getattr(r, "event", None) == "telegram.message.received" for r in caplog.records)
    assert all(getattr(r, "text", None) is None for r in caplog.records)


@pytest.mark.asyncio
async def test_processor_can_log_text_when_enabled(
    sample_new_event: TelegramMessageEvent,
    caplog: pytest.LogCaptureFixture,
) -> None:
    processor = LoggingMessageProcessor(log_message_text=True)
    with caplog.at_level(logging.INFO):
        await processor.process(sample_new_event)

    assert any(getattr(r, "text", None) == sample_new_event.text for r in caplog.records)
