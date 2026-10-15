"""Thin command handlers: authorize, then call the config service."""

from __future__ import annotations

import logging

from aiogram import Router
from aiogram.enums import ParseMode
from aiogram.filters import BaseFilter, Command
from aiogram.types import Message

from app.application.notifications.format import (
    config_help_text,
    config_start_text,
    format_balance,
    format_open_exposure,
    format_runtime_config,
    format_set_error,
    format_set_usage,
)
from app.core.errors import BybitApiError, BybitTransportError, ConfigurationError
from app.core.logging import log_event
from app.infrastructure.bot.deps import OperatorBotDeps

logger = logging.getLogger(__name__)


class AdminFilter(BaseFilter):
    """Allow only configured Telegram user ids."""

    def __init__(self, admin_ids: frozenset[int]) -> None:
        self._admin_ids = admin_ids

    async def __call__(self, message: Message) -> bool:
        user = message.from_user
        return user is not None and user.id in self._admin_ids


def build_router(admin_ids: frozenset[int], deps: OperatorBotDeps) -> Router:
    """Admin commands plus a denial for everyone else."""
    admin = Router()
    admin.message.filter(AdminFilter(admin_ids))

    @admin.message(Command("start"))
    async def start_command(message: Message) -> None:
        await message.answer(config_start_text(deps.config.get()), parse_mode=ParseMode.HTML)

    @admin.message(Command("help"))
    async def help_command(message: Message) -> None:
        await message.answer(config_help_text(), parse_mode=ParseMode.HTML)

    @admin.message(Command("config"))
    async def show_config(message: Message) -> None:
        await message.answer(
            format_runtime_config(deps.config.get()),
            parse_mode=ParseMode.HTML,
        )

    @admin.message(Command("set"))
    async def set_config(message: Message) -> None:
        parts = (message.text or "").split(maxsplit=2)
        if len(parts) < 3:
            await message.answer(format_set_usage(), parse_mode=ParseMode.HTML)
            return
        try:
            updated = deps.config.set_field(parts[1], parts[2])
        except ConfigurationError as exc:
            await message.answer(
                format_set_error(parts[1], str(exc)),
                parse_mode=ParseMode.HTML,
            )
            return
        await message.answer(format_runtime_config(updated), parse_mode=ParseMode.HTML)

    @admin.message(Command("get_balance", "balance"))
    async def get_balance_command(message: Message) -> None:
        gateway = deps.gateway
        if gateway is None:
            await message.answer(
                "Биржа не подключена. Нужен <code>TRADING_MODE=demo</code> "
                "или <code>mainnet</code> при старте программы.",
                parse_mode=ParseMode.HTML,
            )
            return
        try:
            snapshot = await gateway.get_balance()
        except (BybitApiError, BybitTransportError) as exc:
            log_event(
                logger,
                logging.WARNING,
                "bot.balance.failed",
                "Balance request failed",
                error_type=type(exc).__name__,
            )
            await message.answer(f"Не удалось получить баланс: {type(exc).__name__}")
            return
        except Exception as exc:  # noqa: BLE001 — show safe error to operator
            log_event(
                logger,
                logging.WARNING,
                "bot.balance.failed",
                "Balance request failed",
                error_type=type(exc).__name__,
            )
            await message.answer(f"Не удалось получить баланс: {type(exc).__name__}")
            return
        await message.answer(
            format_balance(snapshot, trading_mode=deps.trading_mode),
            parse_mode=ParseMode.HTML,
        )

    @admin.message(Command("get_orders", "orders"))
    async def get_orders_command(message: Message) -> None:
        gateway = deps.gateway
        if gateway is None:
            await message.answer(
                "Биржа не подключена. Нужен <code>TRADING_MODE=demo</code> "
                "или <code>mainnet</code> при старте программы.",
                parse_mode=ParseMode.HTML,
            )
            return
        try:
            positions = await gateway.list_open_positions()
            orders = await gateway.list_open_orders()
        except (BybitApiError, BybitTransportError) as exc:
            log_event(
                logger,
                logging.WARNING,
                "bot.orders.failed",
                "Open orders/positions request failed",
                error_type=type(exc).__name__,
            )
            await message.answer(
                f"Не удалось получить ордера/позиции: {type(exc).__name__}"
            )
            return
        except Exception as exc:  # noqa: BLE001 — show safe error to operator
            log_event(
                logger,
                logging.WARNING,
                "bot.orders.failed",
                "Open orders/positions request failed",
                error_type=type(exc).__name__,
            )
            await message.answer(
                f"Не удалось получить ордера/позиции: {type(exc).__name__}"
            )
            return
        await message.answer(
            format_open_exposure(
                trading_mode=deps.trading_mode,
                positions=positions,
                orders=orders,
            ),
            parse_mode=ParseMode.HTML,
        )

    public = Router()

    @public.message()
    async def denied(message: Message) -> None:
        user = message.from_user
        if user is None or user.id in admin_ids:
            return
        await message.answer("Нет доступа.")

    root = Router()
    root.include_router(admin)
    root.include_router(public)
    return root
