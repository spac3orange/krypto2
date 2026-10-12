"""Telethon client factory."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from telethon import TelegramClient

from app.infrastructure.telegram.proxy import parse_proxy_url
from app.infrastructure.telegram.session import ensure_session_directory


def create_telegram_client(
    *,
    session_path: Path,
    api_id: int,
    api_hash: str,
    catch_up: bool = False,
    proxy_url: str | None = None,
) -> TelegramClient:
    """Create a configured TelegramClient (does not connect)."""
    ensure_session_directory(session_path)
    proxy: dict[str, Any] | None = parse_proxy_url(proxy_url) if proxy_url else None
    return TelegramClient(
        str(session_path),
        api_id,
        api_hash,
        proxy=proxy,
        auto_reconnect=True,
        connection_retries=None,
        retry_delay=1,
        flood_sleep_threshold=60,
        sequential_updates=True,
        catch_up=catch_up,
        receive_updates=True,
    )
