"""Typed application errors."""

from __future__ import annotations


class AppError(Exception):
    """Base application error."""


class ConfigurationError(AppError):
    """Invalid or missing configuration."""


class AuthenticationError(AppError):
    """Telegram session / authentication failure (fatal)."""


class ConnectionError(AppError):  # noqa: A001 — intentional domain name
    """Telegram connection failure."""


class MappingError(AppError):
    """Failed to map an external event to an internal DTO."""


class ProcessingError(AppError):
    """Failed while processing an internal message event."""


class SourceResolutionError(AppError):
    """Configured Telegram source could not be resolved."""


class TradingDisabledError(AppError):
    """Trading subsystem is disabled."""


class SignalValidationError(AppError):
    """Signal failed validation before execution."""

    def __init__(self, reason: str, message: str | None = None) -> None:
        self.reason = reason
        super().__init__(message or reason)


class InstrumentNotFoundError(AppError):
    """Resolved Bybit instrument does not exist."""

    def __init__(self, symbol: str) -> None:
        self.symbol = symbol
        super().__init__(f"instrument_not_found:{symbol}")


class InstrumentConstraintError(AppError):
    """Instrument constraints prevent the intended trade."""

    def __init__(self, reason: str, message: str | None = None) -> None:
        self.reason = reason
        super().__init__(message or reason)


class InsufficientBalanceError(AppError):
    """Available balance is insufficient for the intended margin."""


class ExistingPositionError(AppError):
    """An open position already exists for the symbol."""


class BelowMinNotionalError(InstrumentConstraintError):
    """Sized order is below exchange min notional / qty."""


class BybitTransportError(AppError):
    """Network / transport failure talking to Bybit."""


class BybitApiError(AppError):
    """Bybit returned a business/API error."""

    def __init__(self, ret_code: int | str, ret_msg: str) -> None:
        self.ret_code = ret_code
        self.ret_msg = ret_msg
        super().__init__(f"bybit_api_error:{ret_code}")


class OrderUncertainError(AppError):
    """Order create result is uncertain; reconcile required (no blind retry)."""


class ExecutionTimeoutError(AppError):
    """Timed out waiting for fill confirmation."""


class ExecutionConflictError(AppError):
    """Durable journal already has a record for this event."""
