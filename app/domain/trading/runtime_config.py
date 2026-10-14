"""Runtime trading settings stored outside the process environment."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

from app.domain.trading.enums import OrderSizingPrice, TradingMode


@dataclass(frozen=True, slots=True)
class RuntimeTradingConfig:
    """Editable trading policy. Secrets never live here."""

    trading_mode: TradingMode
    bybit_leverage: Decimal
    trade_margin_pct: Decimal
    order_sizing_price: OrderSizingPrice
    take_profit_enabled: bool
    take_profit_pct: Decimal
    stop_loss_enabled: bool
    stop_loss_pct: Decimal | None
    max_signal_age_seconds: int
    execute_edited_messages: bool
    react_dump: bool
    react_pump: bool
    react_short: bool
    orders_enabled: bool


class RuntimeConfigSource(Protocol):
    """Read the current trading policy (DB or settings snapshot)."""

    def get(self) -> RuntimeTradingConfig:
        """Return the latest config."""


class RuntimeConfigStore(Protocol):
    """SQLite-backed key/value store for runtime trading config."""

    def get_all(self) -> dict[str, str]:
        """Return every stored key."""

    def put_many(self, values: dict[str, str]) -> None:
        """Insert or replace the given keys."""
