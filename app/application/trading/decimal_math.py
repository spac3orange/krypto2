"""Pure Decimal helpers for qty / price rounding (exchange-safe)."""

from __future__ import annotations

from decimal import ROUND_CEILING, ROUND_DOWN, ROUND_FLOOR, Decimal

from app.domain.trading.enums import PositionDirection


def quantize_down(value: Decimal, step: Decimal) -> Decimal:
    """Round ``value`` down to a multiple of ``step`` (never above value)."""
    if step <= 0:
        msg = "step must be > 0"
        raise ValueError(msg)
    units = (value / step).to_integral_value(rounding=ROUND_DOWN)
    return units * step


def quantize_to_tick(
    price: Decimal, tick_size: Decimal, *, direction: PositionDirection
) -> Decimal:
    """Round TP price to tickSize.

    LONG TP: round down (conservative, closer to entry if anything).
    SHORT TP: round up (conservative for short TP below entry... actually for SHORT
    TP is below entry; rounding down keeps TP further/safer? Spec says round to tick.
    Use: LONG → FLOOR, SHORT → CEILING so TP is not less favorable than calculated
    for closing direction... For simplicity: always ROUND_DOWN to tick for LONG TP
    and ROUND_UP for SHORT TP so we don't overshoot the target % unfavorably.
    """
    if tick_size <= 0:
        msg = "tick_size must be > 0"
        raise ValueError(msg)
    units = price / tick_size
    if direction is PositionDirection.LONG:
        rounded = units.to_integral_value(rounding=ROUND_FLOOR)
    else:
        rounded = units.to_integral_value(rounding=ROUND_CEILING)
    return rounded * tick_size


def calc_take_profit_price(
    *,
    avg_entry: Decimal,
    take_profit_pct: Decimal,
    direction: PositionDirection,
    tick_size: Decimal,
) -> Decimal:
    """TP from actual avg entry: LONG +pct, SHORT -pct, then tick-rounded."""
    factor = take_profit_pct / Decimal("100")
    if direction is PositionDirection.LONG:
        raw = avg_entry * (Decimal("1") + factor)
    else:
        raw = avg_entry * (Decimal("1") - factor)
    return quantize_to_tick(raw, tick_size, direction=direction)


def calc_stop_loss_price(
    *,
    avg_entry: Decimal,
    stop_loss_pct: Decimal,
    direction: PositionDirection,
    tick_size: Decimal,
) -> Decimal:
    """SL from avg entry: LONG -pct, SHORT +pct."""
    factor = stop_loss_pct / Decimal("100")
    if direction is PositionDirection.LONG:
        raw = avg_entry * (Decimal("1") - factor)
        # For SL below entry on LONG, ceil would be less protective; floor is safer.
        units = (raw / tick_size).to_integral_value(rounding=ROUND_FLOOR)
    else:
        raw = avg_entry * (Decimal("1") + factor)
        units = (raw / tick_size).to_integral_value(rounding=ROUND_CEILING)
    return units * tick_size
