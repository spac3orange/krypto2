"""Trading domain models (exchange-SDK free)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from app.domain.trading.enums import (
    ExecutionStatus,
    OrderSide,
    PositionDirection,
    TradeAction,
    TradingSignalType,
)


@dataclass(frozen=True, slots=True)
class ParsedTradingSignal:
    """Normalized trading signal independent of transport (Telegram, etc.)."""

    exchange: str
    timeframe: str
    symbol: str
    signal_type: TradingSignalType
    action: TradeAction
    change_percent: Decimal
    price_from: Decimal
    price_to: Decimal
    signal_24h_count: int | None


@dataclass(frozen=True, slots=True)
class ResolvedInstrument:
    """Bybit linear USDT perpetual instrument constraints."""

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
    """Current market prices for sizing / provisional TP."""

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
    """Open position snapshot for a symbol (one-way)."""

    symbol: str
    size: Decimal
    side: str | None
    avg_price: Decimal | None
    leverage: Decimal | None
    position_im: Decimal | None = None
    unrealised_pnl: Decimal | None = None


@dataclass(frozen=True, slots=True)
class OpenOrderSnapshot:
    """Working (open) order on the exchange."""

    symbol: str
    side: str
    order_type: str
    qty: Decimal
    leaves_qty: Decimal
    price: Decimal | None
    order_status: str
    reduce_only: bool
    order_link_id: str


@dataclass(frozen=True, slots=True)
class TakeProfitPlan:
    """Take-profit / optional stop-loss plan."""

    take_profit_price: Decimal | None
    stop_loss_price: Decimal | None
    tp_trigger_by: str
    sl_trigger_by: str | None = None


@dataclass(frozen=True, slots=True)
class TradeIntent:
    """Validated, sized trade ready for submission (no credentials)."""

    correlation_id: str
    source_event_id: str
    order_link_id: str
    symbol: str
    category: str
    side: OrderSide
    direction: PositionDirection
    leverage: Decimal
    target_margin: Decimal
    target_notional: Decimal
    quantity: Decimal
    sizing_price: Decimal
    signal_type: TradingSignalType
    action: TradeAction
    timeframe: str
    take_profit_pct: Decimal | None
    stop_loss_pct: Decimal | None
    tp_trigger_by: str
    provisional_take_profit: Decimal | None
    provisional_stop_loss: Decimal | None


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


@dataclass(frozen=True, slots=True)
class ExecutionRecord:
    """Durable execution journal row."""

    event_id: str
    order_link_id: str
    correlation_id: str
    symbol: str
    side: str
    status: ExecutionStatus
    qty: Decimal | None
    target_margin: Decimal | None
    target_notional: Decimal | None
    bybit_order_id: str | None
    avg_price: Decimal | None
    take_profit_price: Decimal | None
    error_code: str | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime
