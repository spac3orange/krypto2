"""Send operator notices through an aiogram Bot."""

from __future__ import annotations

import logging

from aiogram import Bot
from aiogram.enums import ParseMode

from app.application.notifications.format import format_order_notice, format_signal_notice
from app.core.logging import log_event
from app.domain.notifications.models import OrderNotice, SignalNotice

logger = logging.getLogger(__name__)


class AiogramOperatorNotifier:
    """Broadcasts to the configured admin chats. Failures are logged, not raised."""

    def __init__(self, bot: Bot, chat_ids: frozenset[int]) -> None:
        self._bot = bot
        self._chat_ids = chat_ids

    async def signal_detected(self, notice: SignalNotice) -> None:
        await self._broadcast(format_signal_notice(notice))

    async def order_update(self, notice: OrderNotice) -> None:
        await self._broadcast(format_order_notice(notice))

    async def _broadcast(self, text: str) -> None:
        for chat_id in self._chat_ids:
            try:
                await self._bot.send_message(chat_id, text, parse_mode=ParseMode.HTML)
            except Exception as exc:  # noqa: BLE001 — notification must not stop trading
                log_event(
                    logger,
                    logging.WARNING,
                    "bot.notify.failed",
                    "Operator notification was not delivered",
                    chat_id=chat_id,
                    error_type=type(exc).__name__,
                )
