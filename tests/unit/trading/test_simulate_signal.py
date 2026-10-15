"""Unit tests for the demo-trading signal simulator (no network)."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest
from app.application.trading.signal_parser import parse_trading_signal
from app.core.errors import ConfigurationError
from app.domain.trading.enums import TradeAction, TradingMode, TradingSignalType
from app.tools.simulate_signal import (
    format_bot_message,
    load_signal_file,
    normalize_symbol,
    normalize_timeframe,
    price_bounds,
    require_demo,
    resolve_signal_specs,
    signed_change,
)

_FIXTURE = Path(__file__).resolve().parents[3] / "data" / "trading" / "test_signals.json"


def test_require_demo_rejects_mainnet_and_disabled() -> None:
    require_demo(TradingMode.DEMO)
    with pytest.raises(ConfigurationError):
        require_demo(TradingMode.MAINNET)
    with pytest.raises(ConfigurationError):
        require_demo(TradingMode.DISABLED)


def test_normalize_symbol_strips_usdt_suffix() -> None:
    assert normalize_symbol("btc") == "BTC"
    assert normalize_symbol("ETHUSDT") == "ETH"
    assert normalize_symbol("1000PEPE") == "1000PEPE"


def test_normalize_symbol_rejects_blank() -> None:
    with pytest.raises(ConfigurationError):
        normalize_symbol("  ")


def test_normalize_timeframe() -> None:
    assert normalize_timeframe("15M") == "15m"
    with pytest.raises(ConfigurationError):
        normalize_timeframe("10min")


def test_pump_message_roundtrip() -> None:
    change = signed_change(TradingSignalType.PUMP, Decimal("10"))
    price_from, price_to = price_bounds(Decimal("110"), change)
    text = format_bot_message(
        symbol="BTC",
        timeframe="10m",
        signal_type=TradingSignalType.PUMP,
        change_percent=change,
        price_from=price_from,
        price_to=price_to,
    )
    signal = parse_trading_signal(text).signal
    assert signal is not None
    assert signal.symbol == "BTC"
    assert signal.signal_type is TradingSignalType.PUMP
    assert signal.action is TradeAction.SELL
    assert signal.change_percent == Decimal("10")
    assert signal.price_to == Decimal("110")


def test_short_message_roundtrip() -> None:
    change = signed_change(TradingSignalType.SHORT, Decimal("10"))
    price_from, price_to = price_bounds(Decimal("110"), change)
    text = format_bot_message(
        symbol="BTC",
        timeframe="10m",
        signal_type=TradingSignalType.SHORT,
        change_percent=change,
        price_from=price_from,
        price_to=price_to,
    )
    signal = parse_trading_signal(text).signal
    assert signal is not None
    assert signal.signal_type is TradingSignalType.SHORT
    assert signal.action is TradeAction.SELL
    assert "🔴" in text


def test_dump_message_roundtrip() -> None:
    change = signed_change(TradingSignalType.DUMP, Decimal("10"))
    price_from, price_to = price_bounds(Decimal("90"), change)
    text = format_bot_message(
        symbol="ETH",
        timeframe="15m",
        signal_type=TradingSignalType.DUMP,
        change_percent=change,
        price_from=price_from,
        price_to=price_to,
    )
    signal = parse_trading_signal(text).signal
    assert signal is not None
    assert signal.signal_type is TradingSignalType.DUMP
    assert signal.action is TradeAction.BUY
    assert signal.change_percent == Decimal("-10")
    assert signal.price_from == Decimal("100")
    assert signal.price_to == Decimal("90")


def test_load_signal_file_parses_rows(tmp_path: Path) -> None:
    path = tmp_path / "signals.json"
    path.write_text(
        json.dumps(
            {
                "signals": [
                    {"symbol": "btcusdt", "side": "dump", "change": "5", "timeframe": "10m"},
                    {"symbol": "ETH", "side": "pump", "change": 4, "signal_24h": 2},
                ]
            }
        ),
        encoding="utf-8",
    )
    specs = load_signal_file(path)
    assert specs[0].symbol == "BTC"
    assert specs[0].signal_type is TradingSignalType.DUMP
    assert specs[0].change_percent == Decimal("-5")
    assert specs[1].symbol == "ETH"
    assert specs[1].timeframe == "10m"
    assert specs[1].change_percent == Decimal("4")
    assert specs[1].signal_24h_count == 2


def test_load_signal_file_rejects_duplicate_symbol(tmp_path: Path) -> None:
    path = tmp_path / "signals.json"
    path.write_text(
        json.dumps(
            {
                "signals": [
                    {"symbol": "BTC", "side": "dump", "change": "5"},
                    {"symbol": "BTCUSDT", "side": "pump", "change": "4"},
                ]
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ConfigurationError, match="Duplicate symbol"):
        load_signal_file(path)


def test_load_signal_file_rejects_float_change(tmp_path: Path) -> None:
    path = tmp_path / "signals.json"
    path.write_text(
        json.dumps({"signals": [{"symbol": "BTC", "side": "dump", "change": 1.5}]}),
        encoding="utf-8",
    )
    with pytest.raises(ConfigurationError, match="string or integer"):
        load_signal_file(path)


def test_shipped_test_signals_are_unique_and_varied() -> None:
    specs = load_signal_file(_FIXTURE)
    assert len(specs) == 6
    assert len({spec.symbol for spec in specs}) == 6
    assert {spec.signal_type for spec in specs} == {
        TradingSignalType.PUMP,
        TradingSignalType.DUMP,
    }


def test_resolve_signal_specs_rejects_mixing_file_and_symbol() -> None:
    with pytest.raises(ConfigurationError, match="not both"):
        resolve_signal_specs(
            file="signals.json",
            symbol="BTC",
            side="dump",
            change=None,
            timeframe=None,
        )
