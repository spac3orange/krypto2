"""Unit tests for trading signal parser."""

from __future__ import annotations

from decimal import Decimal

from app.application.trading.signal_parser import parse_trading_signal
from app.domain.trading.enums import TradeAction, TradingSignalType


def test_saga_pump_with_emoji() -> None:
    text = "⚫ ByBit – 10m – SAGA\n🔴 Pump: 26.93% (0.071523-0.090782)\n📡 Signal 24h: 1"
    result = parse_trading_signal(text)
    assert result.signal is not None
    signal = result.signal
    assert signal.exchange == "BYBIT"
    assert signal.timeframe == "10m"
    assert signal.symbol == "SAGA"
    assert signal.signal_type is TradingSignalType.PUMP
    assert signal.action is TradeAction.SELL
    assert signal.change_percent == Decimal("26.93")
    assert signal.price_from == Decimal("0.071523")
    assert signal.price_to == Decimal("0.090782")
    assert signal.signal_24h_count == 1


def test_btr_dump_with_emoji() -> None:
    text = "⚫ ByBit – 15m – BTR\n🔻 Dump: -15.95% (0.06031-0.05069)\n📡 Signal 24h: 1"
    signal = parse_trading_signal(text).signal
    assert signal is not None
    assert signal.symbol == "BTR"
    assert signal.timeframe == "15m"
    assert signal.signal_type is TradingSignalType.DUMP
    assert signal.action is TradeAction.BUY
    assert signal.change_percent == Decimal("-15.95")
    assert signal.price_from == Decimal("0.06031")
    assert signal.price_to == Decimal("0.05069")
    assert signal.signal_24h_count == 1


def test_br_dump() -> None:
    text = "⚫ ByBit – 15m – BR\n🔻 Dump: -15.15% (1.16527-0.98875)\n📡 Signal 24h: 1"
    signal = parse_trading_signal(text).signal
    assert signal is not None
    assert signal.symbol == "BR"
    assert signal.signal_type is TradingSignalType.DUMP
    assert signal.action is TradeAction.BUY
    assert signal.change_percent == Decimal("-15.15")
    assert signal.price_from == Decimal("1.16527")
    assert signal.price_to == Decimal("0.98875")


def test_lyn_pump_green_emoji() -> None:
    text = "⚫ ByBit – 10m – LYN\n🟢 Pump: 21.2% (0.0425-0.05151)\n📡 Signal 24h: 1"
    signal = parse_trading_signal(text).signal
    assert signal is not None
    assert signal.symbol == "LYN"
    assert signal.signal_type is TradingSignalType.PUMP
    assert signal.action is TradeAction.SELL
    assert signal.change_percent == Decimal("21.2")
    assert signal.price_from == Decimal("0.0425")
    assert signal.price_to == Decimal("0.05151")


def test_without_emoji() -> None:
    text = "ByBit - 10m - BTC\nPump: 20% (1.2-1.44)\nSignal 24h: 2"
    signal = parse_trading_signal(text).signal
    assert signal is not None
    assert signal.symbol == "BTC"
    assert signal.signal_type is TradingSignalType.PUMP
    assert signal.action is TradeAction.SELL
    assert signal.change_percent == Decimal("20")
    assert signal.price_from == Decimal("1.2")
    assert signal.price_to == Decimal("1.44")
    assert signal.signal_24h_count == 2


def test_lowercase_pump() -> None:
    text = "ByBit – 10m – BTC\npump: 20% (1-1.2)\nSignal 24h: 1"
    signal = parse_trading_signal(text).signal
    assert signal is not None
    assert signal.signal_type is TradingSignalType.PUMP
    assert signal.action is TradeAction.SELL
    assert signal.change_percent == Decimal("20")
    assert signal.price_from == Decimal("1")
    assert signal.price_to == Decimal("1.2")


def test_extra_whitespace() -> None:
    text = (
        "  ByBit  –  15m  –  DOGE  \n  Dump :  -10.5%   (  0.1  –  0.09  )  \n  Signal 24h :  15  "
    )
    signal = parse_trading_signal(text).signal
    assert signal is not None
    assert signal.symbol == "DOGE"
    assert signal.timeframe == "15m"
    assert signal.signal_type is TradingSignalType.DUMP
    assert signal.action is TradeAction.BUY
    assert signal.change_percent == Decimal("-10.5")
    assert signal.price_from == Decimal("0.1")
    assert signal.price_to == Decimal("0.09")
    assert signal.signal_24h_count == 15


def test_ordinary_message_returns_none() -> None:
    result = parse_trading_signal("hello world")
    assert result.signal is None
    assert result.rejection_reason is None


def test_pump_without_symbol_rejected() -> None:
    text = "Pump: 26.93% (0.071523-0.090782)\nSignal 24h: 1"
    result = parse_trading_signal(text)
    assert result.signal is None
    assert result.rejection_reason == "invalid_format"


def test_pump_without_price_range_rejected() -> None:
    text = "ByBit – 10m – SAGA\nPump: 26.93%\nSignal 24h: 1"
    result = parse_trading_signal(text)
    assert result.signal is None
    assert result.rejection_reason == "missing_price_range"


def test_symbol_1000pepe() -> None:
    text = "ByBit - 5m - 1000PEPE\nDump: -12% (0.01-0.0088)\nSignal 24h: 3"
    signal = parse_trading_signal(text).signal
    assert signal is not None
    assert signal.symbol == "1000PEPE"
    assert signal.timeframe == "5m"
    assert signal.signal_type is TradingSignalType.DUMP
    assert signal.action is TradeAction.BUY


def test_unicode_dash_hyphen() -> None:
    text = "ByBit - 10m - AAA\nPump: 10% (1-1.1)\nSignal 24h: 1"
    assert parse_trading_signal(text).signal is not None


def test_unicode_dash_en() -> None:
    text = "ByBit – 10m – AAA\nPump: 10% (1–1.1)\nSignal 24h: 1"
    signal = parse_trading_signal(text).signal
    assert signal is not None
    assert signal.price_from == Decimal("1")
    assert signal.price_to == Decimal("1.1")


def test_unicode_dash_em() -> None:
    text = "ByBit — 1h — WIF\nDump: -5% (2—1.9)\nSignal 24h: 1"
    signal = parse_trading_signal(text).signal
    assert signal is not None
    assert signal.timeframe == "1h"
    assert signal.symbol == "WIF"
    assert signal.signal_type is TradingSignalType.DUMP


def test_direction_from_word_not_percent_sign() -> None:
    """Odd data still maps by word Dump → BUY, not by percent magnitude."""
    text = "ByBit - 10m - XYZ\nDump: 15% (1-1.15)\nSignal 24h: 1"
    signal = parse_trading_signal(text).signal
    assert signal is not None
    assert signal.signal_type is TradingSignalType.DUMP
    assert signal.action is TradeAction.BUY
    assert signal.change_percent == Decimal("15")


def test_compact_header_no_spaces() -> None:
    text = "ByBit–10m–SAGA\nPump: 26.93% (0.071523-0.090782)\nSignal 24h: 1"
    signal = parse_trading_signal(text).signal
    assert signal is not None
    assert signal.symbol == "SAGA"
    assert signal.timeframe == "10m"
