"""Application runtime entry: Telegram ingestion (+ optional trading)."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import signal
import sys
from types import FrameType

from app.application.notifications.null_notifier import NullOperatorNotifier
from app.application.telegram.message_processor import LoggingMessageProcessor
from app.application.trading.bootstrap import TradingSubsystem, build_trading_subsystem
from app.application.trading.runtime_config_service import RuntimeConfigService
from app.core.config import load_settings
from app.core.errors import (
    AppError,
    AuthenticationError,
    ConfigurationError,
    SourceResolutionError,
)
from app.core.logging import log_event, setup_logging
from app.domain.notifications.ports import OperatorNotifier
from app.infrastructure.bot.service import OperatorBotService
from app.infrastructure.persistence.sqlite_runtime_config import SqliteRuntimeConfigStore
from app.infrastructure.telegram.service import TelegramIngestionService

logger = logging.getLogger(__name__)


async def run_ingestion() -> None:
    """Validate config, optional trading preflight, start Telegram ingestion."""
    settings = load_settings()
    setup_logging(settings.log_level, log_dir=settings.log_dir)
    log_event(
        logger,
        logging.INFO,
        "app.logging.ready",
        "Logging configured",
        log_dir=str(settings.log_dir.resolve()),
        log_level=settings.log_level,
    )

    config_service = RuntimeConfigService(
        settings,
        SqliteRuntimeConfigStore(settings.execution_db_path),
    )
    config_service.seed()
    notifier: OperatorNotifier = NullOperatorNotifier()
    bot: OperatorBotService | None = None
    if settings.telegram_bot_token:
        bot = OperatorBotService(
            token=settings.telegram_bot_token,
            admin_ids=settings.telegram_bot_admin_ids,
            config=config_service,
            proxy_url=settings.proxy_url,
        )
        await bot.start()
        if bot.notifier is not None:
            notifier = bot.notifier
    else:
        log_event(
            logger,
            logging.WARNING,
            "bot.disabled",
            "Operator bot not started: TELEGRAM_BOT_TOKEN is empty",
        )

    trading: TradingSubsystem | None = await build_trading_subsystem(
        settings,
        config_source=config_service,
        notifier=notifier,
    )
    if bot is not None and trading is not None:
        bot.attach_exchange(trading.gateway, trading_mode=settings.trading_mode.value)
    processor = LoggingMessageProcessor(
        log_message_text=settings.log_telegram_message_text,
        orchestrator=trading.orchestrator if trading else None,
        notifier=notifier,
    )
    service = TelegramIngestionService(settings, processor=processor)
    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    def _request_shutdown(signame: str) -> None:
        if stop_event.is_set():
            log_event(
                logger,
                logging.WARNING,
                "telegram.shutdown",
                "Forced process exit on repeated shutdown signal",
                signal=signame,
            )
            os._exit(1)

        log_event(
            logger,
            logging.INFO,
            "telegram.shutdown",
            "Received shutdown signal",
            signal=signame,
        )
        stop_event.set()
        loop.call_soon_threadsafe(
            lambda: asyncio.create_task(
                service.shutdown(),
                name="telegram-signal-shutdown",
            )
        )

    for signame in ("SIGINT", "SIGTERM"):
        sig = getattr(signal, signame, None)
        if sig is None:
            continue
        try:
            loop.add_signal_handler(sig, _request_shutdown, signame)
        except NotImplementedError:
            if signame == "SIGINT":

                def _win_sigint(_signum: int, _frame: FrameType | None) -> None:
                    _request_shutdown("SIGINT")

                signal.signal(signal.SIGINT, _win_sigint)

    async def _lifecycle() -> None:
        await service.start()
        await service.run()

    life_task = asyncio.create_task(_lifecycle(), name="telegram-lifecycle")
    stop_task = asyncio.create_task(stop_event.wait(), name="telegram-stop")

    done, pending = await asyncio.wait(
        {life_task, stop_task},
        return_when=asyncio.FIRST_COMPLETED,
    )

    for task in pending:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    run_error: BaseException | None = None
    if life_task in done and not stop_event.is_set():
        try:
            life_task.result()
        except Exception as exc:  # noqa: BLE001 — re-raise after cleanup
            run_error = exc
    elif life_task.cancelled() or stop_event.is_set():
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await life_task

    await service.shutdown()
    if bot is not None:
        await bot.stop()
    if trading is not None:
        await trading.gateway.close()

    if run_error is not None:
        raise run_error


def main() -> None:
    """CLI entrypoint for ``python -m app``."""
    try:
        asyncio.run(run_ingestion())
    except ConfigurationError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
    except (AuthenticationError, SourceResolutionError) as exc:
        print(f"Fatal error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    except AppError as exc:
        print(f"Application error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    except KeyboardInterrupt:
        raise SystemExit(0) from None


if __name__ == "__main__":
    main()
