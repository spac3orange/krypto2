"""Processor integration with trading signal parsing."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

import pytest
from app.application.telegram.message_processor import LoggingMessageProcessor
from app.domain.telegram.enums import TelegramEventType
from app.domain.telegram.models import TelegramMessageEvent


def _event(text: str) -> TelegramMessageEvent:
    return TelegramMessageEvent(
        event_id="telegram:-100123:456:new",
        event_type=TelegramEventType.NEW_MESSAGE,
        chat_id=-100123,
        message_id=456,
        sender_id=1,
        sender_username="bot",
        chat_username=None,
        text=text,
        date=datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
        edit_date=None,
        received_at=datetime(2026, 1, 1, 12, 0, 1, tzinfo=UTC),
        has_media=False,
        reply_to_message_id=None,
    )


@pytest.mark.asyncio
async def test_processor_logs_detected_signal(caplog: pytest.LogCaptureFixture) -> None:
    text = "⚫ ByBit – 10m – SAGA\n🔴 Pump: 26.93% (0.071523-0.090782)\n📡 Signal 24h: 1"
    processor = LoggingMessageProcessor(log_message_text=False)
    with caplog.at_level(logging.INFO):
        await processor.process(_event(text))

    detected = [r for r in caplog.records if getattr(r, "event", None) == "trading.signal.detected"]
    assert len(detected) == 1
    record = detected[0]
    assert record.exchange == "BYBIT"
    assert record.symbol == "SAGA"
    assert record.signal_type == "PUMP"
    assert record.action == "SELL"
    assert record.change_percent == "26.93"
    assert record.price_from == "0.071523"
    assert record.price_to == "0.090782"
    assert record.signal_24h_count == 1
    assert record.event_id == "telegram:-100123:456:new"
    assert not hasattr(record, "text") or getattr(record, "text", None) is None


@pytest.mark.asyncio
async def test_processor_logs_rejection(caplog: pytest.LogCaptureFixture) -> None:
    text = "ByBit – 10m – SAGA\nPump: 26.93%\nSignal 24h: 1"
    processor = LoggingMessageProcessor()
    with caplog.at_level(logging.WARNING):
        await processor.process(_event(text))

    rejected = [r for r in caplog.records if getattr(r, "event", None) == "trading.signal.rejected"]
    assert len(rejected) == 1
    assert rejected[0].reason == "missing_price_range"


@pytest.mark.asyncio
async def test_processor_ignores_non_signal(caplog: pytest.LogCaptureFixture) -> None:
    processor = LoggingMessageProcessor()
    with caplog.at_level(logging.INFO):
        await processor.process(_event("hello world"))

    events = {getattr(r, "event", None) for r in caplog.records}
    assert "trading.signal.detected" not in events
    assert "trading.signal.rejected" not in events
    assert "telegram.message.received" in events
