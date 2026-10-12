"""Position sizing from equity % + leverage (Decimal only)."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.application.trading.decimal_math import quantize_down
from app.core.errors import (
    BelowMinNotionalError,
    InstrumentConstraintError,
    InsufficientBalanceError,
)
from app.domain.trading.models import AccountSnapshot, MarketTicker, ResolvedInstrument


@dataclass(frozen=True, slots=True)
class SizedPosition:
    """Result of allocation → qty sizing."""

    target_margin: Decimal
    target_notional: Decimal
    quantity: Decimal
    sizing_price: Decimal


class PositionSizer:
    """Compute market qty from TRADE_MARGIN_PCT without exceeding allocation."""

    def size(
        self,
        *,
        account: AccountSnapshot,
        instrument: ResolvedInstrument,
        ticker: MarketTicker,
        trade_margin_pct: Decimal,
        leverage: Decimal,
        sizing_price: Decimal,
    ) -> SizedPosition:
        if trade_margin_pct <= 0 or trade_margin_pct > Decimal("100"):
            raise InstrumentConstraintError("invalid_margin_pct")
        if leverage < Decimal("1"):
            raise InstrumentConstraintError("invalid_leverage")
        if sizing_price <= 0:
            raise InstrumentConstraintError("invalid_pricing")

        target_margin = (account.total_equity * trade_margin_pct) / Decimal("100")
        if target_margin <= 0:
            raise InsufficientBalanceError("insufficient_available_balance")
        if account.total_available_balance < target_margin:
            raise InsufficientBalanceError("insufficient_available_balance")

        if leverage > instrument.max_leverage:
            raise InstrumentConstraintError("leverage_above_max")
        if leverage < instrument.min_leverage:
            raise InstrumentConstraintError("leverage_below_min")

        target_notional = target_margin * leverage
        raw_qty = target_notional / sizing_price
        qty = quantize_down(raw_qty, instrument.qty_step)

        if qty < instrument.min_order_qty:
            raise BelowMinNotionalError("below_min_order_qty")

        notional = qty * sizing_price
        if notional < instrument.min_notional_value:
            # Never bump qty to satisfy exchange minimum — reject.
            raise BelowMinNotionalError("below_min_notional")

        if qty > instrument.max_mkt_order_qty:
            raise InstrumentConstraintError("above_max_mkt_order_qty")

        # Final notional must not exceed configured allocation (within step).
        if notional > target_notional:
            raise InstrumentConstraintError("allocation_exceeded")

        return SizedPosition(
            target_margin=target_margin,
            target_notional=target_notional,
            quantity=qty,
            sizing_price=sizing_price,
        )
