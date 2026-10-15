"""Long-polling operator bot."""

from __future__ import annotations

import asyncio
import contextlib
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession

from app.application.trading.runtime_config_service import RuntimeConfigService
from app.core.logging import log_event
from app.domain.trading.ports import TradingGateway
from app.infrastructure.bot.deps import OperatorBotDeps
from app.infrastructure.bot.handlers import build_router
from app.infrastructure.bot.notifier import AiogramOperatorNotifier
from app.infrastructure.telegram.proxy import proxy_log_fields, proxy_url_for_aiogram

logger = logging.getLogger(__name__)


def create_operator_bot(token: str, proxy_url: str | None) -> Bot:
    """Build the operator bot. Uses ``PROXY_URL`` when it is set."""
    if not proxy_url:
        return Bot(token=token)
    session = AiohttpSession(proxy=proxy_url_for_aiogram(proxy_url))
    return Bot(token=token, session=session)


class OperatorBotService:
    """Aiogram polling task. Does not own trading or Telethon."""

    def __init__(
        self,
        *,
        token: str,
        admin_ids: frozenset[int],
        config: RuntimeConfigService,
        proxy_url: str | None = None,
    ) -> None:
        self._token = token
        self._admin_ids = admin_ids
        self._proxy_url = proxy_url
        self._deps = OperatorBotDeps(config=config)
        self._bot: Bot | None = None
        self._dispatcher: Dispatcher | None = None
        self._poll_task: asyncio.Task[None] | None = None
        self.notifier: AiogramOperatorNotifier | None = None

    def attach_exchange(
        self,
        gateway: TradingGateway,
        *,
        trading_mode: str,
    ) -> None:
        """Wire Bybit gateway after trading preflight (enables /get_balance)."""
        self._deps.gateway = gateway
        self._deps.trading_mode = trading_mode

    async def start(self) -> None:
        bot = create_operator_bot(self._token, self._proxy_url)
        dispatcher = Dispatcher()
        dispatcher.include_router(build_router(self._admin_ids, self._deps))
        self._bot = bot
        self._dispatcher = dispatcher
        self.notifier = AiogramOperatorNotifier(bot, self._admin_ids)
        self._poll_task = asyncio.create_task(
            dispatcher.start_polling(bot, handle_signals=False),
            name="operator-bot",
        )
        log_event(
            logger,
            logging.INFO,
            "bot.started",
            "Operator bot polling started",
            admin_count=len(self._admin_ids),
            **proxy_log_fields(self._proxy_url),
        )

    async def stop(self) -> None:
        if self._dispatcher is not None:
            await self._dispatcher.stop_polling()
        if self._poll_task is not None:
            self._poll_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._poll_task
            self._poll_task = None
        if self._bot is not None:
            await self._bot.session.close()
            self._bot = None
        log_event(logger, logging.INFO, "bot.stopped", "Operator bot stopped")
