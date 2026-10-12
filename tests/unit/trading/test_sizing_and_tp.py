"""Unit tests for position sizing and TP/SL math."""

from __future__ import annotations

from decimal import Decimal

import pytest
from app.application.trading.decimal_math import (
    calc_stop_loss_price,
    calc_take_profit_price,
    quantize_down,
)
from app.application.trading.position_sizer import PositionSizer
from app.core.errors import BelowMinNotionalError, InstrumentConstraintError
from app.domain.trading.enums import PositionDirection
from app.domain.trading.models import AccountSnapshot, MarketTicker, ResolvedInstrument


def _instrument(**kwargs: object) -> ResolvedInstrument:
    base = dict(
        symbol="SAGAUSDT",
        status="Trading",
        contract_type="LinearPerpetual",
        base_coin="SAGA",
        quote_coin="USDT",
        settle_coin="USDT",
        min_leverage=Decimal("1"),
        max_leverage=Decimal("50"),
        leverage_step=Decimal("0.01"),
        min_notional_value=Decimal("5"),
        min_order_qty=Decimal("1"),
        qty_step=Decimal("1"),
        max_mkt_order_qty=Decimal("100000"),
        tick_size=Decimal("0.0001"),
    )
    base.update(kwargs)
    return ResolvedInstrument(**base)  # type: ignore[arg-type]


def test_example_sizing_equity_100_margin_1pct_lev_5_price_10() -> None:
    account = AccountSnapshot(
        total_equity=Decimal("100"),
        total_available_balance=Decimal("100"),
        margin_mode="REGULAR_MARGIN",
        unified_margin_status=5,
    )
    instrument = _instrument(
        symbol="TESTUSDT",
        qty_step=Decimal("0.1"),
        min_order_qty=Decimal("0.1"),
        min_notional_value=Decimal("1"),
    )
    ticker = MarketTicker(symbol="TESTUSDT", last_price=Decimal("10"), mark_price=Decimal("10"))
    sized = PositionSizer().size(
        account=account,
        instrument=instrument,
        ticker=ticker,
        trade_margin_pct=Decimal("1"),
        leverage=Decimal("5"),
        sizing_price=Decimal("10"),
    )
    assert sized.target_margin == Decimal("1")
    assert sized.target_notional == Decimal("5")
    assert sized.quantity == Decimal("0.5")
    assert sized.quantity * sized.sizing_price <= sized.target_notional


def test_saga_example_qty_10() -> None:
    account = AccountSnapshot(
        total_equity=Decimal("100"),
        total_available_balance=Decimal("100"),
        margin_mode="REGULAR_MARGIN",
        unified_margin_status=5,
    )
    instrument = _instrument(min_notional_value=Decimal("5"))
    ticker = MarketTicker(symbol="SAGAUSDT", last_price=Decimal("0.50"), mark_price=Decimal("0.50"))
    sized = PositionSizer().size(
        account=account,
        instrument=instrument,
        ticker=ticker,
        trade_margin_pct=Decimal("1"),
        leverage=Decimal("5"),
        sizing_price=Decimal("0.50"),
    )
    assert sized.quantity == Decimal("10")


def test_qty_step_rounds_down() -> None:
    assert quantize_down(Decimal("10.9"), Decimal("1")) == Decimal("10")
    assert quantize_down(Decimal("0.59"), Decimal("0.1")) == Decimal("0.5")


def test_never_bump_qty_for_min_notional() -> None:
    account = AccountSnapshot(
        total_equity=Decimal("10"),
        total_available_balance=Decimal("10"),
        margin_mode="REGULAR_MARGIN",
        unified_margin_status=5,
    )
    # 1% of 10 = 0.1 margin * 5 lev = 0.5 notional at price 10 => qty 0.05 → below min
    instrument = _instrument(
        qty_step=Decimal("0.01"),
        min_order_qty=Decimal("0.01"),
        min_notional_value=Decimal("5"),
        max_mkt_order_qty=Decimal("1000"),
    )
    ticker = MarketTicker(symbol="SAGAUSDT", last_price=Decimal("10"), mark_price=Decimal("10"))
    with pytest.raises(BelowMinNotionalError):
        PositionSizer().size(
            account=account,
            instrument=instrument,
            ticker=ticker,
            trade_margin_pct=Decimal("1"),
            leverage=Decimal("5"),
            sizing_price=Decimal("10"),
        )


def test_leverage_above_max_rejected() -> None:
    account = AccountSnapshot(
        total_equity=Decimal("100"),
        total_available_balance=Decimal("100"),
        margin_mode="REGULAR_MARGIN",
        unified_margin_status=5,
    )
    instrument = _instrument(max_leverage=Decimal("3"))
    ticker = MarketTicker(symbol="SAGAUSDT", last_price=Decimal("0.5"), mark_price=Decimal("0.5"))
    with pytest.raises(InstrumentConstraintError) as exc:
        PositionSizer().size(
            account=account,
            instrument=instrument,
            ticker=ticker,
            trade_margin_pct=Decimal("1"),
            leverage=Decimal("5"),
            sizing_price=Decimal("0.5"),
        )
    assert exc.value.reason == "leverage_above_max"


def test_long_take_profit_formula() -> None:
    tp = calc_take_profit_price(
        avg_entry=Decimal("0.501"),
        take_profit_pct=Decimal("2"),
        direction=PositionDirection.LONG,
        tick_size=Decimal("0.0001"),
    )
    # 0.501 * 1.02 = 0.51102 → floor to 0.5110
    assert tp == Decimal("0.5110")


def test_short_take_profit_formula() -> None:
    tp = calc_take_profit_price(
        avg_entry=Decimal("0.50"),
        take_profit_pct=Decimal("2"),
        direction=PositionDirection.SHORT,
        tick_size=Decimal("0.0001"),
    )
    # 0.50 * 0.98 = 0.49 → ceil to 0.4900
    assert tp == Decimal("0.4900")


def test_stop_loss_long_short() -> None:
    sl_long = calc_stop_loss_price(
        avg_entry=Decimal("100"),
        stop_loss_pct=Decimal("2"),
        direction=PositionDirection.LONG,
        tick_size=Decimal("0.1"),
    )
    sl_short = calc_stop_loss_price(
        avg_entry=Decimal("100"),
        stop_loss_pct=Decimal("2"),
        direction=PositionDirection.SHORT,
        tick_size=Decimal("0.1"),
    )
    assert sl_long == Decimal("98.0")
    assert sl_short == Decimal("102.0")
