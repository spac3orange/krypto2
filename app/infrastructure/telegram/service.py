"""Telegram ingestion service lifecycle."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from telethon import TelegramClient, events
from telethon.errors import AuthKeyError, AuthKeyUnregisteredError

from app.application.telegram.deduplicator import InMemoryEventDeduplicator
from app.application.telegram.message_processor import LoggingMessageProcessor
from app.core.config import Settings
from app.core.errors import AuthenticationError, SourceResolutionError
from app.core.logging import log_event
from app.domain.telegram.ports import EventDeduplicator, MessageProcessor
from app.infrastructure.telegram.client import create_telegram_client
from app.infrastructure.telegram.handlers import TelegramEventHandlers
from app.infrastructure.telegram.proxy import proxy_log_fields
from app.infrastructure.telegram.session import session_file_exists

logger = logging.getLogger(__name__)

_DISCONNECT_TIMEOUT_SEC = 10.0


def _entity_type_name(entity: Any) -> str:
    bot = getattr(entity, "bot", None)
    if bot is True:
        return "bot"
    # Telethon entity classes
    class_name = type(entity).__name__.lower()
    if "channel" in class_name:
        return "channel"
    if "chat" in class_name:
        return "group"
    if "user" in class_name:
        return "user"
    return "unknown"


class TelegramIngestionService:
    """Owns Telethon connection lifecycle for message ingestion."""

    def __init__(
        self,
        settings: Settings,
        *,
        processor: MessageProcessor | None = None,
        deduplicator: EventDeduplicator | None = None,
        client: TelegramClient | None = None,
    ) -> None:
        self._settings = settings
        self._processor = processor or LoggingMessageProcessor(
            log_message_text=settings.log_telegram_message_text,
        )
        self._deduplicator = deduplicator or InMemoryEventDeduplicator()
        self._client = client or create_telegram_client(
            session_path=settings.telegram_session_path,
            api_id=settings.telegram_api_id,
            api_hash=settings.telegram_api_hash,
            catch_up=settings.telegram_catch_up_enabled,
            proxy_url=settings.proxy_url,
        )
        self._source_entity: Any | None = None
        self._source_chat_id: int | None = None
        self._ready = False
        self._handlers: TelegramEventHandlers | None = None
        self._shutdown_lock = asyncio.Lock()
        self._shutdown_done = False

    @property
    def is_ready(self) -> bool:
        return self._ready

    @property
    def client(self) -> TelegramClient:
        return self._client

    async def start(self) -> None:
        """Connect, authorize, resolve source, register handlers, optional catch-up."""
        self._clear_ready_marker()
        self._ready = False

        if not session_file_exists(self._settings.telegram_session_path):
            log_event(
                logger,
                logging.ERROR,
                "telegram.auth.invalid",
                "Telegram session file is missing; run auth bootstrap first",
            )
            raise AuthenticationError(
                "Telegram session not found. Run: python -m app.telegram.auth"
            )

        log_event(
            logger,
            logging.INFO,
            "telegram.connecting",
            "Connecting to Telegram",
            **proxy_log_fields(self._settings.proxy_url),
        )
        try:
            await self._client.connect()
        except asyncio.CancelledError:
            raise
        except (AuthKeyError, AuthKeyUnregisteredError) as exc:
            log_event(
                logger,
                logging.ERROR,
                "telegram.auth.invalid",
                "Telegram authorization key is invalid",
            )
            raise AuthenticationError("Telegram session is invalid or revoked") from exc

        if self._shutdown_done:
            raise asyncio.CancelledError

        if not await self._client.is_user_authorized():
            log_event(
                logger,
                logging.ERROR,
                "telegram.auth.invalid",
                "Telegram client is not authorized",
            )
            raise AuthenticationError(
                "Telegram session is not authorized. Run: python -m app.telegram.auth"
            )

        log_event(logger, logging.INFO, "telegram.connected", "Connected to Telegram")

        await self._resolve_source()
        assert self._source_chat_id is not None
        assert self._source_entity is not None

        self._handlers = TelegramEventHandlers(
            processor=self._processor,
            deduplicator=self._deduplicator,
            expected_chat_id=self._source_chat_id,
        )
        self._client.add_event_handler(
            self._handlers.handle_new_message,
            events.NewMessage(chats=self._source_entity),
        )
        self._client.add_event_handler(
            self._handlers.handle_message_edited,
            events.MessageEdited(chats=self._source_entity),
        )

        if self._settings.telegram_catch_up_enabled:
            await self._client.catch_up()

        if self._shutdown_done:
            raise asyncio.CancelledError

        self._ready = True
        self._write_ready_marker()

    async def run(self) -> None:
        """Block until the client disconnects."""
        await self._client.run_until_disconnected()

    async def shutdown(self) -> None:
        """Gracefully disconnect and clear readiness (idempotent)."""
        async with self._shutdown_lock:
            if self._shutdown_done:
                return
            self._shutdown_done = True

            log_event(
                logger,
                logging.INFO,
                "telegram.shutdown",
                "Shutting down Telegram client",
            )
            self._ready = False
            self._clear_ready_marker()

            # Always call disconnect — aborts in-progress connect/reconnect loops.
            try:
                await asyncio.wait_for(
                    self._client.disconnect(),
                    timeout=_DISCONNECT_TIMEOUT_SEC,
                )
            except TimeoutError:
                log_event(
                    logger,
                    logging.WARNING,
                    "telegram.shutdown",
                    "Telegram disconnect timed out",
                )
            except Exception:
                logger.debug(
                    "Telegram disconnect raised during shutdown",
                    exc_info=True,
                )

            log_event(
                logger,
                logging.INFO,
                "telegram.disconnected",
                "Telegram client disconnected",
            )

    async def _resolve_source(self) -> None:
        source = self._settings.telegram_source
        try:
            entity = await self._client.get_entity(source)
        except (ValueError, TypeError) as exc:
            raise SourceResolutionError("Configured Telegram source could not be resolved") from exc
        except Exception as exc:
            raise SourceResolutionError("Configured Telegram source is unavailable") from exc

        chat_id = int(entity.id)
        # Normalize to Telethon peer id when available
        try:
            chat_id = int(await self._client.get_peer_id(entity))
        except Exception:
            chat_id = int(entity.id)

        username = getattr(entity, "username", None)
        log_event(
            logger,
            logging.INFO,
            "telegram.source.resolved",
            "Telegram source resolved",
            type=_entity_type_name(entity),
            username=username,
            id=chat_id,
        )
        self._source_entity = entity
        self._source_chat_id = chat_id

    def _write_ready_marker(self) -> None:
        path = self._settings.telegram_ready_marker_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("ready\n", encoding="utf-8")

    def _clear_ready_marker(self) -> None:
        path = self._settings.telegram_ready_marker_path
        try:
            path.unlink(missing_ok=True)
        except OSError:
            logger.debug("Failed to clear readiness marker", extra={"path": str(path)})
