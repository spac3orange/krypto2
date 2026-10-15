"""Deterministic pure parser for pump/dump trading signal messages."""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from app.domain.trading.enums import TradeAction, TradingSignalType
from app.domain.trading.models import ParsedTradingSignal

# Unicode dash variants commonly used in Telegram/typographic text.
_DASH = r"[-–—−]"

# Latin m/h and Cyrillic м/ч (as in «10м» from pump_screener_bot).
_HEADER_RE = re.compile(
    rf"(?i)\bbybit\b\s*{_DASH}\s*(\d+[mhмч])\s*{_DASH}\s*([A-Za-z0-9]+)\b",
)

_SIGNAL_LINE_RE = re.compile(
    rf"(?i)([🟢🔴🔻])?\s*(pump|dump)\s*:\s*"
    rf"(-?\d+(?:\.\d+)?)\s*%\s*"
    rf"\(\s*(-?\d+(?:\.\d+)?)\s*{_DASH}\s*(-?\d+(?:\.\d+)?)\s*\)",
)

_SIGNAL_24H_RE = re.compile(
    r"(?i)signal\s*24h\s*:\s*(\d+)",
)

_PUMP_OR_DUMP_WORD_RE = re.compile(r"(?i)\b(pump|dump)\b")

# Pump (any colour) → short; Dump → long.
_ACTION_BY_TYPE = {
    TradingSignalType.PUMP: TradeAction.SELL,
    TradingSignalType.SHORT: TradeAction.SELL,
    TradingSignalType.DUMP: TradeAction.BUY,
}

_TIMEFRAME_CYRILLIC = str.maketrans({"м": "m", "ч": "h", "М": "m", "Ч": "h"})


@dataclass(frozen=True, slots=True)
class SignalParseResult:
    """Outcome of attempting to parse a trading signal from text."""

    signal: ParsedTradingSignal | None = None
    rejection_reason: str | None = None

    @property
    def is_signal(self) -> bool:
        return self.signal is not None

    @property
    def is_rejected(self) -> bool:
        return self.rejection_reason is not None


def _classify_signal_type(*, word: str, emoji: str | None) -> TradingSignalType:
    """Map screener emoji + Pump/Dump word to an internal signal type.

    Direction is always short for Pump (green or red); Dump is long.
    Emoji only splits toggles: 🟢 → REACT_PUMP, 🔴 → REACT_SHORT.
    """
    kind = word.upper()
    if kind == "DUMP":
        return TradingSignalType.DUMP
    if emoji == "🟢":
        return TradingSignalType.PUMP
    if emoji == "🔴":
        return TradingSignalType.SHORT
    # No emoji: same as red Pump (short / REACT_SHORT).
    return TradingSignalType.SHORT


def _normalize_timeframe(raw: str) -> str:
    return raw.translate(_TIMEFRAME_CYRILLIC).lower()


def parse_trading_signal(text: str) -> SignalParseResult:
    """Parse signal text into ``ParsedTradingSignal`` or a rejection.

    - Ordinary non-signal text → empty result (not an error).
    - Pump/Dump present but incomplete/invalid → ``rejection_reason`` set.
    - Complete valid signal → ``signal`` set.
    """
    if not text or not text.strip():
        return SignalParseResult()

    if not _PUMP_OR_DUMP_WORD_RE.search(text):
        return SignalParseResult()

    header = _HEADER_RE.search(text)
    if header is None:
        return SignalParseResult(rejection_reason="invalid_format")

    timeframe = _normalize_timeframe(header.group(1))
    symbol = header.group(2).upper()
    if not symbol:
        return SignalParseResult(rejection_reason="missing_symbol")

    signal_match = _SIGNAL_LINE_RE.search(text)
    if signal_match is None:
        if re.search(r"(?i)\b(pump|dump)\s*:", text) and not re.search(
            r"\(\s*-?\d",
            text,
        ):
            return SignalParseResult(rejection_reason="missing_price_range")
        if not re.search(r"(?i)\b(pump|dump)\s*:\s*-?\d", text):
            return SignalParseResult(rejection_reason="invalid_percentage")
        return SignalParseResult(rejection_reason="invalid_format")

    emoji = signal_match.group(1)
    signal_type = _classify_signal_type(word=signal_match.group(2), emoji=emoji)
    action = _ACTION_BY_TYPE[signal_type]

    try:
        change_percent = Decimal(signal_match.group(3))
        price_from = Decimal(signal_match.group(4))
        price_to = Decimal(signal_match.group(5))
    except InvalidOperation:
        return SignalParseResult(rejection_reason="invalid_percentage")

    signal_24h_count: int | None = None
    count_match = _SIGNAL_24H_RE.search(text)
    if count_match is not None:
        signal_24h_count = int(count_match.group(1))

    signal = ParsedTradingSignal(
        exchange="BYBIT",
        timeframe=timeframe,
        symbol=symbol,
        signal_type=signal_type,
        action=action,
        change_percent=change_percent,
        price_from=price_from,
        price_to=price_to,
        signal_24h_count=signal_24h_count,
    )
    return SignalParseResult(signal=signal)


class TradingSignalParser:
    """Application adapter implementing the SignalParser port."""

    def parse(self, text: str) -> ParsedTradingSignal | None:
        return parse_trading_signal(text).signal

    def parse_detailed(self, text: str) -> SignalParseResult:
        return parse_trading_signal(text)
