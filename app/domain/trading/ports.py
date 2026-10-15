"""Ports for trading application services."""

from __future__ import annotations

from decimal import Decimal
from typing import Protocol

from app.domain.trading.enums import ExecutionStatus, OrderSide
from app.domain.trading.models import (
    AccountSnapshot,
    ExecutionRecord,
    MarketTicker,
    OpenOrderSnapshot,
    OrderExecution,
    OrderSubmission,
    ParsedTradingSignal,
    PositionSnapshot,
    ResolvedInstrument,
    TakeProfitPlan,
)


class SignalParser(Protocol):
    """Parses raw text into a trading signal (or rejects / ignores)."""

    def parse(self, text: str) -> ParsedTradingSignal | None:
        """Return a signal, or ``None`` when the text is not a usable signal."""


class TradingGateway(Protocol):
    """Exchange adapter for account / market / order operations."""

    async def get_api_key_info(self) -> dict[str, object]:
        """Validate API key and return safe metadata (no secrets)."""

    async def get_account_info(self) -> AccountSnapshot:
        """Fetch account info; equity fields may be filled by get_balance."""

    async def get_balance(self) -> AccountSnapshot:
        """Fetch UNIFIED wallet balance + merge account metadata."""

    async def get_instrument(self, symbol: str) -> ResolvedInstrument | None:
        """Resolve linear instrument info or None if missing."""

    async def get_ticker(self, symbol: str) -> MarketTicker:
        """Fetch last/mark prices."""

    async def get_position(self, symbol: str) -> PositionSnapshot:
        """Fetch one-way position for symbol (size may be zero)."""

    async def list_open_positions(self) -> list[PositionSnapshot]:
        """List non-zero positions for settle coin (linear)."""

    async def list_open_orders(self) -> list[OpenOrderSnapshot]:
        """List working open orders for settle coin (linear)."""

    async def set_leverage(self, symbol: str, leverage: Decimal) -> None:
        """Set buy/sell leverage equally (one-way)."""

    async def place_order(
        self,
        *,
        symbol: str,
        side: OrderSide,
        qty: Decimal,
        order_link_id: str,
        take_profit: Decimal | None = None,
        stop_loss: Decimal | None = None,
        tp_trigger_by: str | None = None,
        sl_trigger_by: str | None = None,
    ) -> OrderSubmission:
        """Submit a market order. Must NOT blind-retry on uncertainty."""

    async def get_order_by_link_id(self, symbol: str, order_link_id: str) -> OrderExecution | None:
        """Lookup order by deterministic orderLinkId (realtime then history)."""

    async def set_trading_stop(
        self,
        *,
        symbol: str,
        plan: TakeProfitPlan,
    ) -> None:
        """Install / adjust full-position TP/SL."""

    async def wait_for_fill(
        self,
        *,
        symbol: str,
        order_link_id: str,
        timeout_sec: float,
    ) -> OrderExecution:
        """Wait for fill via WS and/or REST reconcile; never place a new order."""


class ExecutionStore(Protocol):
    """Durable execution journal for crash-safe idempotency."""

    def get_by_event_id(self, event_id: str) -> ExecutionRecord | None:
        """Return existing record or None."""

    def get_by_order_link_id(self, order_link_id: str) -> ExecutionRecord | None:
        """Return existing record or None."""

    def reserve(
        self,
        *,
        event_id: str,
        order_link_id: str,
        correlation_id: str,
        symbol: str,
        side: str,
    ) -> ExecutionRecord:
        """Insert RESERVED row; raise if event_id already exists."""

    def update(
        self,
        event_id: str,
        *,
        status: ExecutionStatus,
        qty: Decimal | None = None,
        target_margin: Decimal | None = None,
        target_notional: Decimal | None = None,
        bybit_order_id: str | None = None,
        avg_price: Decimal | None = None,
        take_profit_price: Decimal | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> ExecutionRecord:
        """Update journal row."""
