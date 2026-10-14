"""DTOs returned by the Bybit gateway (SDK-free)."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .enums import OrderSide


@dataclass(frozen=True, slots=True)
class ResolvedInstrument:
    """Linear USDT perpetual instrument constraints."""

    symbol: str
    status: str
    contract_type: str
    base_coin: str
    quote_coin: str
    settle_coin: str
    min_leverage: Decimal
    max_leverage: Decimal
    leverage_step: Decimal
    min_notional_value: Decimal
    min_order_qty: Decimal
    qty_step: Decimal
    max_mkt_order_qty: Decimal
    tick_size: Decimal


@dataclass(frozen=True, slots=True)
class MarketTicker:
    """Last / mark prices for sizing."""

    symbol: str
    last_price: Decimal
    mark_price: Decimal


@dataclass(frozen=True, slots=True)
class AccountSnapshot:
    """Unified account equity snapshot."""

    total_equity: Decimal
    total_available_balance: Decimal
    margin_mode: str
    unified_margin_status: int | None
    account_type: str = "UNIFIED"


@dataclass(frozen=True, slots=True)
class PositionSnapshot:
    """One-way position for a symbol (size may be zero)."""

    symbol: str
    size: Decimal
    side: str | None
    avg_price: Decimal | None
    leverage: Decimal | None


@dataclass(frozen=True, slots=True)
class TakeProfitPlan:
    """Full-position TP / optional SL."""

    take_profit_price: Decimal | None
    stop_loss_price: Decimal | None
    tp_trigger_by: str
    sl_trigger_by: str | None = None


@dataclass(frozen=True, slots=True)
class OrderSubmission:
    """Exchange acknowledgement of order create."""

    order_id: str
    order_link_id: str
    symbol: str
    side: OrderSide
    qty: Decimal
    status: str


@dataclass(frozen=True, slots=True)
class OrderExecution:
    """Confirmed fill / execution state."""

    order_id: str
    order_link_id: str
    symbol: str
    side: OrderSide
    qty: Decimal
    filled_qty: Decimal
    avg_price: Decimal | None
    status: str
    cum_exec_qty: Decimal | None = None
