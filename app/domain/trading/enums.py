"""Trading domain enums."""

from __future__ import annotations

from enum import StrEnum


class TradingSignalType(StrEnum):
    """Signal category from @pump_screener_bot (by emoji / word)."""

    PUMP = "PUMP"  # 🟢 Pump → long alert
    SHORT = "SHORT"  # 🔴 Pump → short alert
    DUMP = "DUMP"  # 🔻 Dump


class TradeAction(StrEnum):
    """Logical trade action derived from signal type (not an exchange order)."""

    BUY = "BUY"
    SELL = "SELL"


class TradingMode(StrEnum):
    """Runtime trading mode (never defaults to mainnet)."""

    DISABLED = "disabled"
    DEMO = "demo"
    MAINNET = "mainnet"


class OrderSide(StrEnum):
    """Bybit order side for linear perpetuals."""

    BUY = "Buy"
    SELL = "Sell"


class PositionDirection(StrEnum):
    """Resulting position direction after opening."""

    LONG = "LONG"
    SHORT = "SHORT"


class ExecutionStatus(StrEnum):
    """Durable execution journal statuses."""

    RESERVED = "reserved"
    SUBMITTING = "submitting"
    SUBMITTED = "submitted"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    TP_SET = "tp_set"
    COMPLETED = "completed"
    REJECTED = "rejected"
    FAILED = "failed"
    SKIPPED = "skipped"
    RECONCILED = "reconciled"


class ExistingPositionPolicy(StrEnum):
    """Policy when an open position already exists for the symbol."""

    SKIP = "skip"


class OrderSizingPrice(StrEnum):
    """Price source used for quantity sizing."""

    LAST_PRICE = "lastPrice"
    MARK_PRICE = "markPrice"
