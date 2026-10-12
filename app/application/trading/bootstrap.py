"""Compose trading subsystem from settings (factory)."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from app.application.trading.orchestrator import TradingSignalOrchestrator
from app.core.config import Settings
from app.core.errors import BybitApiError, ConfigurationError
from app.core.logging import log_event
from app.domain.notifications.ports import OperatorNotifier
from app.domain.trading.enums import TradingMode
from app.domain.trading.runtime_config import RuntimeConfigSource
from app.infrastructure.bybit.client import create_bybit_http
from app.infrastructure.bybit.gateway import BybitGateway
from app.infrastructure.persistence.sqlite_execution_store import SqliteExecutionStore

logger = logging.getLogger(__name__)


def describe_preflight_failure(exc: BaseException) -> tuple[str, str]:
    """Map a Bybit preflight error to a reason code and a safe message."""
    if isinstance(exc, BybitApiError) and str(exc.ret_code) == "10002":
        return (
            "clock_skew",
            "Bybit rejected the request because the system clock is out of sync "
            "(retCode 10002). Sync the Windows clock and start again.",
        )
    if isinstance(exc, BybitApiError) and str(exc.ret_code) == "10003":
        return ("api_key_invalid", "Bybit API key validation failed")
    return ("preflight_failed", "Bybit preflight failed")


@dataclass(slots=True)
class TradingSubsystem:
    """Running trading components (optional when TRADING_MODE=disabled)."""

    gateway: BybitGateway
    store: SqliteExecutionStore
    orchestrator: TradingSignalOrchestrator


async def build_trading_subsystem(
    settings: Settings,
    *,
    config_source: RuntimeConfigSource | None = None,
    notifier: OperatorNotifier | None = None,
) -> TradingSubsystem | None:
    """Create and preflight trading stack, or None when disabled."""
    if settings.trading_mode is TradingMode.DISABLED:
        log_event(
            logger,
            logging.INFO,
            "trading.preflight.ok",
            "Trading subsystem disabled",
            trading_mode=settings.trading_mode.value,
        )
        return None

    if settings.bybit_api_key is None or settings.bybit_api_secret is None:
        raise ConfigurationError("Bybit API credentials missing")

    http = create_bybit_http(
        api_key=settings.bybit_api_key,
        api_secret=settings.bybit_api_secret,
        demo=settings.bybit_demo,
    )
    gateway = BybitGateway(
        http,
        category=settings.bybit_category,
        settle_coin=settings.bybit_settle_coin,
        demo=settings.bybit_demo,
        api_key=settings.bybit_api_key,
        api_secret=settings.bybit_api_secret,
    )
    await gateway.start()

    # API key check — never log secrets.
    try:
        key_info = await gateway.get_api_key_info()
        log_event(
            logger,
            logging.INFO,
            "trading.preflight.ok",
            "Bybit API key validated",
            trading_mode=settings.trading_mode.value,
            api_key_id=key_info.get("id"),
            read_only=key_info.get("readOnly"),
        )
    except Exception as exc:
        reason, message = describe_preflight_failure(exc)
        log_event(
            logger,
            logging.ERROR,
            "trading.preflight.failed",
            message,
            reason=reason,
            error_type=type(exc).__name__,
        )
        raise ConfigurationError(message) from exc

    account = await gateway.get_account_info()
    if settings.bybit_expected_margin_mode:
        expected = settings.bybit_expected_margin_mode.strip().upper()
        actual = (account.margin_mode or "").strip().upper()
        if expected and actual and expected != actual:
            log_event(
                logger,
                logging.ERROR,
                "trading.preflight.failed",
                "Unexpected Bybit margin mode",
                reason="unexpected_margin_mode",
                expected=expected,
                actual=actual,
            )
            raise ConfigurationError(f"Unexpected margin mode: expected {expected}, got {actual}")

    balance = await gateway.get_balance()
    log_event(
        logger,
        logging.INFO,
        "trading.preflight.ok",
        "Bybit account preflight passed",
        trading_mode=settings.trading_mode.value,
        margin_mode=balance.margin_mode,
        unified_margin_status=balance.unified_margin_status,
        total_equity=str(balance.total_equity),
        # Do not log API secrets; equity is fine.
    )

    store = SqliteExecutionStore(settings.execution_db_path)
    orchestrator = TradingSignalOrchestrator(
        settings,
        gateway=gateway,
        store=store,
        config_source=config_source,
        notifier=notifier,
    )
    return TradingSubsystem(gateway=gateway, store=store, orchestrator=orchestrator)
