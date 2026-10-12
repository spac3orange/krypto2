"""Thin command handlers: authorize, then call the config service."""

from __future__ import annotations

from aiogram import Router
from aiogram.enums import ParseMode
from aiogram.filters import BaseFilter, Command
from aiogram.types import Message

from app.application.notifications.format import (
    config_help_text,
    config_start_text,
    format_runtime_config,
)
from app.application.trading.runtime_config_service import RuntimeConfigService
from app.core.errors import ConfigurationError


class AdminFilter(BaseFilter):
    """Allow only configured Telegram user ids."""

    def __init__(self, admin_ids: frozenset[int]) -> None:
        self._admin_ids = admin_ids

    async def __call__(self, message: Message) -> bool:
        user = message.from_user
        return user is not None and user.id in self._admin_ids


def build_router(admin_ids: frozenset[int], config: RuntimeConfigService) -> Router:
    """Admin commands plus a denial for everyone else."""
    admin = Router()
    admin.message.filter(AdminFilter(admin_ids))

    @admin.message(Command("start"))
    async def start_command(message: Message) -> None:
        await message.answer(config_start_text())

    @admin.message(Command("help"))
    async def help_command(message: Message) -> None:
        await message.answer(config_help_text(), parse_mode=ParseMode.HTML)

    @admin.message(Command("config"))
    async def show_config(message: Message) -> None:
        await message.answer(format_runtime_config(config.get()), parse_mode=ParseMode.HTML)

    @admin.message(Command("set"))
    async def set_config(message: Message) -> None:
        parts = (message.text or "").split(maxsplit=2)
        if len(parts) < 3:
            await message.answer("Формат: /set КЛЮЧ ЗНАЧЕНИЕ")
            return
        try:
            updated = config.set_field(parts[1], parts[2])
        except ConfigurationError as exc:
            await message.answer(f"Ошибка: {exc}")
            return
        await message.answer(format_runtime_config(updated), parse_mode=ParseMode.HTML)

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
