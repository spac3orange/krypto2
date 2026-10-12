"""Ports for Telegram application services."""

from __future__ import annotations

from typing import Protocol

from app.domain.telegram.models import TelegramMessageEvent


class MessageProcessor(Protocol):
    """Consumes normalized Telegram message events."""

    async def process(self, event: TelegramMessageEvent) -> None:
        """Handle a single Telegram message event."""


class EventDeduplicator(Protocol):
    """Tracks seen event IDs to suppress duplicate delivery."""

    def seen(self, event_id: str) -> bool:
        """Return True if ``event_id`` was already observed; otherwise record it."""
