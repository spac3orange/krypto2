"""Interactive Telegram user-session bootstrap."""

from __future__ import annotations

import asyncio
import logging
import sys

from app.core.config import load_auth_settings
from app.core.errors import AuthenticationError, ConfigurationError
from app.core.logging import log_event, setup_logging
from app.infrastructure.telegram.client import create_telegram_client
from app.infrastructure.telegram.proxy import proxy_log_fields
from app.infrastructure.telegram.session import ensure_session_directory

logger = logging.getLogger(__name__)


async def authorize() -> None:
    """Run interactive Telethon login and persist the session file."""
    settings = load_auth_settings()
    setup_logging(settings.log_level, log_dir=settings.log_dir)
    ensure_session_directory(settings.telegram_session_path)

    client = create_telegram_client(
        session_path=settings.telegram_session_path,
        api_id=settings.telegram_api_id,
        api_hash=settings.telegram_api_hash,
        catch_up=False,
        proxy_url=settings.proxy_url,
    )

    log_event(
        logger,
        logging.INFO,
        "telegram.connecting",
        "Starting Telegram authorization bootstrap",
        **proxy_log_fields(settings.proxy_url),
    )
    # Telethon prompts for phone / code / 2FA interactively via start().
    await client.start()

    if not await client.is_user_authorized():
        log_event(
            logger,
            logging.ERROR,
            "telegram.auth.invalid",
            "Authorization finished without an authorized session",
        )
        await client.disconnect()
        raise AuthenticationError("Telegram authorization failed")

    me = await client.get_me()
    log_event(
        logger,
        logging.INFO,
        "telegram.connected",
        "Telegram session authorized successfully",
        user_id=getattr(me, "id", None),
        username=getattr(me, "username", None),
    )
    await client.disconnect()
    log_event(
        logger,
        logging.INFO,
        "telegram.disconnected",
        "Auth bootstrap disconnected cleanly",
    )


def main() -> None:
    """CLI entrypoint for ``python -m app.telegram.auth``."""
    try:
        asyncio.run(authorize())
    except ConfigurationError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
    except AuthenticationError as exc:
        print(f"Authentication error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
