"""Inject synthetic pump/dump notifications into the Bybit Demo Trading pipeline.

The text matches the Telegram bot format. It is parsed and executed by the same
processor and orchestrator as a live message. Telegram is not contacted.

Refuses to run unless ``TRADING_MODE=demo``.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from app.application.telegram.message_processor import LoggingMessageProcessor
from app.application.trading.bootstrap import TradingSubsystem, build_trading_subsystem
from app.application.trading.signal_parser import parse_trading_signal
from app.core.config import load_settings
from app.core.errors import AppError, ConfigurationError
from app.core.logging import setup_logging
from app.domain.telegram.enums import TelegramEventType
from app.domain.telegram.event_id import build_event_id
from app.domain.telegram.models import TelegramMessageEvent
from app.domain.trading.enums import TradingMode, TradingSignalType

# Distinct from any real Telegram chat so journal rows are obvious.
SIMULATED_CHAT_ID = -1_000_000_000_001
BATCH_PAUSE_SECONDS = 1.0

_TIMEFRAME_RE = re.compile(r"\d+[mh]")
_SYMBOL_RE = re.compile(r"[A-Z0-9]+")
_TOP_LEVEL_KEYS = frozenset({"description", "signals"})
_SIGNAL_KEYS = frozenset({"symbol", "side", "change", "timeframe", "signal_24h"})
_REQUIRED_SIGNAL_KEYS = frozenset({"symbol", "side", "change"})


@dataclass(frozen=True, slots=True)
class SimulatedSignalSpec:
    """One bot notification to inject."""

    symbol: str
    timeframe: str
    signal_type: TradingSignalType
    change_percent: Decimal
    signal_24h_count: int


def require_demo(mode: TradingMode) -> None:
    """Hard stop: this tool must never submit mainnet (or disabled) orders."""
    if mode is TradingMode.DEMO:
        return
    msg = "simulate_signal refuses to run unless TRADING_MODE=demo"
    raise ConfigurationError(msg)


def normalize_symbol(raw: str) -> str:
    """Ticker as the bot prints it (no USDT suffix)."""
    symbol = raw.strip().upper()
    if symbol.endswith("USDT") and len(symbol) > 4:
        symbol = symbol[:-4]
    if not _SYMBOL_RE.fullmatch(symbol):
        msg = f"Invalid symbol {raw!r}; expected a ticker such as BTC or 1000PEPE"
        raise ConfigurationError(msg)
    return symbol


def normalize_timeframe(raw: str) -> str:
    timeframe = raw.strip().lower()
    if not _TIMEFRAME_RE.fullmatch(timeframe):
        msg = f"Invalid timeframe {raw!r}; expected a value like 10m or 1h"
        raise ConfigurationError(msg)
    return timeframe


def parse_side(raw: str) -> TradingSignalType:
    key = raw.strip().lower()
    if key in {"pump", "long"}:
        return TradingSignalType.PUMP
    if key == "short":
        return TradingSignalType.SHORT
    if key == "dump":
        return TradingSignalType.DUMP
    msg = "side must be pump, short, or dump"
    raise ConfigurationError(msg)


def signed_change(signal_type: TradingSignalType, magnitude: Decimal) -> Decimal:
    """Bot-style percent: pump positive, dump negative."""
    if magnitude <= 0 or magnitude >= Decimal("90"):
        msg = "change must satisfy 0 < value < 90"
        raise ConfigurationError(msg)
    if signal_type is TradingSignalType.DUMP:
        return -magnitude
    return magnitude


def parse_change(raw: str) -> Decimal:
    try:
        return Decimal(raw)
    except InvalidOperation as exc:
        msg = f"Invalid change percent {raw!r}"
        raise ConfigurationError(msg) from exc


def price_bounds(last_price: Decimal, change_percent: Decimal) -> tuple[Decimal, Decimal]:
    """Range ending at the live last price (parser-only; orders use the exchange price)."""
    if last_price <= 0:
        msg = "last price must be > 0"
        raise ConfigurationError(msg)
    start = last_price / (Decimal("1") + (change_percent / Decimal("100")))
    return start, last_price


def format_decimal(value: Decimal) -> str:
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def format_bot_message(
    *,
    symbol: str,
    timeframe: str,
    signal_type: TradingSignalType,
    change_percent: Decimal,
    price_from: Decimal,
    price_to: Decimal,
    signal_24h_count: int = 1,
) -> str:
    """Text in the same shape as pump-screener notifications."""
    if signal_type is TradingSignalType.PUMP:
        emoji = "🟢"
        label = "Pump"
    elif signal_type is TradingSignalType.SHORT:
        emoji = "🔴"
        label = "Pump"
    else:
        emoji = "🔻"
        label = "Dump"
    change = format_decimal(change_percent)
    start = format_decimal(price_from)
    end = format_decimal(price_to)
    return (
        f"⚫ ByBit – {timeframe} – {symbol}\n"
        f"{emoji} {label}: {change}% ({start}-{end})\n"
        f"📡 Signal 24h: {signal_24h_count}"
    )


def build_simulated_event(text: str, *, message_id: int) -> TelegramMessageEvent:
    now = datetime.now(UTC)
    event_type = TelegramEventType.NEW_MESSAGE
    return TelegramMessageEvent(
        event_id=build_event_id(
            chat_id=SIMULATED_CHAT_ID,
            message_id=message_id,
            event_type=event_type,
        ),
        event_type=event_type,
        chat_id=SIMULATED_CHAT_ID,
        message_id=message_id,
        sender_id=None,
        sender_username="simulated_signal",
        chat_username="simulated_signal",
        text=text,
        date=now,
        edit_date=None,
        received_at=now,
        has_media=False,
        reply_to_message_id=None,
    )


def _object_dict(value: object, *, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        msg = f"{label} must be a JSON object"
        raise ConfigurationError(msg)
    result: dict[str, object] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            msg = f"{label} has a non-string key"
            raise ConfigurationError(msg)
        result[key] = item
    return result


def _parse_change_field(value: object, *, label: str) -> Decimal:
    if isinstance(value, bool | float):
        msg = f"{label} change must be a string or integer"
        raise ConfigurationError(msg)
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, str):
        return parse_change(value)
    msg = f"{label} change must be a string or integer"
    raise ConfigurationError(msg)


def _parse_signal_24h(value: object, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        msg = f"{label} signal_24h must be an integer"
        raise ConfigurationError(msg)
    if value < 1:
        msg = f"{label} signal_24h must be >= 1"
        raise ConfigurationError(msg)
    return value


def _parse_signal_object(value: object, *, index: int) -> SimulatedSignalSpec:
    label = f"signals[{index}]"
    row = _object_dict(value, label=label)
    unknown = set(row) - _SIGNAL_KEYS
    if unknown:
        names = ", ".join(sorted(unknown))
        msg = f"{label} has unknown fields: {names}"
        raise ConfigurationError(msg)
    missing = _REQUIRED_SIGNAL_KEYS - set(row)
    if missing:
        names = ", ".join(sorted(missing))
        msg = f"{label} is missing fields: {names}"
        raise ConfigurationError(msg)

    symbol_raw = row["symbol"]
    side_raw = row["side"]
    timeframe_raw = row.get("timeframe", "10m")
    if not isinstance(symbol_raw, str):
        msg = f"{label} symbol must be a string"
        raise ConfigurationError(msg)
    if not isinstance(side_raw, str):
        msg = f"{label} side must be a string"
        raise ConfigurationError(msg)
    if not isinstance(timeframe_raw, str):
        msg = f"{label} timeframe must be a string"
        raise ConfigurationError(msg)

    signal_type = parse_side(side_raw)
    signal_24h = 1
    if "signal_24h" in row:
        signal_24h = _parse_signal_24h(row["signal_24h"], label=label)
    return SimulatedSignalSpec(
        symbol=normalize_symbol(symbol_raw),
        timeframe=normalize_timeframe(timeframe_raw),
        signal_type=signal_type,
        change_percent=signed_change(signal_type, _parse_change_field(row["change"], label=label)),
        signal_24h_count=signal_24h,
    )


def load_signal_file(path: Path) -> list[SimulatedSignalSpec]:
    """Load a JSON list of signals. Each symbol may appear only once."""
    if not path.is_file():
        msg = f"Signal file not found: {path}"
        raise ConfigurationError(msg)
    try:
        payload: object = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        msg = f"Signal file is not valid JSON: {path}"
        raise ConfigurationError(msg) from exc

    document = _object_dict(payload, label="signal file")
    unknown = set(document) - _TOP_LEVEL_KEYS
    if unknown:
        names = ", ".join(sorted(unknown))
        msg = f"Signal file has unknown fields: {names}"
        raise ConfigurationError(msg)
    if "description" in document and not isinstance(document["description"], str):
        msg = "Signal file description must be a string"
        raise ConfigurationError(msg)
    raw_signals = document.get("signals")
    if not isinstance(raw_signals, list) or not raw_signals:
        msg = "Signal file signals must be a non-empty array"
        raise ConfigurationError(msg)

    specs = [_parse_signal_object(item, index=index) for index, item in enumerate(raw_signals)]
    seen: set[str] = set()
    for spec in specs:
        if spec.symbol in seen:
            msg = f"Duplicate symbol in signal file: {spec.symbol}"
            raise ConfigurationError(msg)
        seen.add(spec.symbol)
    return specs


def resolve_signal_specs(
    *,
    file: str | None,
    symbol: str | None,
    side: str | None,
    change: str | None,
    timeframe: str | None,
) -> list[SimulatedSignalSpec]:
    """CLI: either a JSON file or one ``--symbol`` / ``--side`` signal."""
    has_single = any(value is not None for value in (symbol, side, change, timeframe))
    if file is not None and has_single:
        msg = "Pass either --file or --symbol/--side/--change/--timeframe, not both"
        raise ConfigurationError(msg)
    if file is not None:
        return load_signal_file(Path(file))
    if symbol is None or side is None:
        msg = "Pass --file or both --symbol and --side"
        raise ConfigurationError(msg)
    signal_type = parse_side(side)
    magnitude = parse_change("5" if change is None else change)
    return [
        SimulatedSignalSpec(
            symbol=normalize_symbol(symbol),
            timeframe=normalize_timeframe("10m" if timeframe is None else timeframe),
            signal_type=signal_type,
            change_percent=signed_change(signal_type, magnitude),
            signal_24h_count=1,
        )
    ]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Simulate pump/dump bot notifications and run them through the "
            "Bybit Demo Trading pipeline. Does not connect to Telegram."
        ),
    )
    parser.add_argument(
        "--file",
        help="JSON file of signals, e.g. data/trading/test_signals.json",
    )
    parser.add_argument("--symbol", help="Ticker, e.g. BTC or ETHUSDT")
    parser.add_argument("--side", choices=("pump", "short", "dump", "long"))
    parser.add_argument(
        "--change",
        help="Move size in percent, without sign (default: 5). Dump is stored as negative.",
    )
    parser.add_argument("--timeframe", help="Signal timeframe (default: 10m)")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the messages and parsed signals; do not place orders",
    )
    return parser


async def _inject_spec(
    trading: TradingSubsystem,
    processor: LoggingMessageProcessor,
    spec: SimulatedSignalSpec,
    *,
    message_id: int,
    dry_run: bool,
) -> None:
    ticker = await trading.gateway.get_ticker(f"{spec.symbol}USDT")
    price_from, price_to = price_bounds(ticker.last_price, spec.change_percent)
    text = format_bot_message(
        symbol=spec.symbol,
        timeframe=spec.timeframe,
        signal_type=spec.signal_type,
        change_percent=spec.change_percent,
        price_from=price_from,
        price_to=price_to,
        signal_24h_count=spec.signal_24h_count,
    )
    print(text, file=sys.stderr)

    parsed = parse_trading_signal(text)
    if parsed.signal is None:
        msg = f"Simulated text failed to parse ({parsed.rejection_reason})"
        raise ConfigurationError(msg)

    if dry_run:
        print(
            f"dry-run {parsed.signal.signal_type.value} {parsed.signal.symbol} "
            f"→ {parsed.signal.action.value} last={ticker.last_price}",
            file=sys.stderr,
        )
        return

    event = build_simulated_event(text, message_id=message_id)
    await processor.process(event)
    print(
        f"injected {event.event_id} {parsed.signal.signal_type.value} "
        f"{parsed.signal.symbol} → {parsed.signal.action.value}",
        file=sys.stderr,
    )


async def run(argv: list[str] | None = None) -> None:
    args = _build_parser().parse_args(argv)
    specs = resolve_signal_specs(
        file=args.file,
        symbol=args.symbol,
        side=args.side,
        change=args.change,
        timeframe=args.timeframe,
    )
    settings = load_settings()
    setup_logging(settings.log_level)
    require_demo(settings.trading_mode)

    trading = await build_trading_subsystem(settings)
    if trading is None:
        raise ConfigurationError("Trading subsystem did not start")

    processor = LoggingMessageProcessor(
        log_message_text=True,
        orchestrator=trading.orchestrator,
    )
    failures: list[str] = []
    base_message_id = time.time_ns() // 1_000_000
    try:
        for index, spec in enumerate(specs):
            label = f"{index + 1}/{len(specs)} {spec.symbol} {spec.signal_type.value}"
            print(f"--- {label} ---", file=sys.stderr)
            try:
                await _inject_spec(
                    trading,
                    processor,
                    spec,
                    message_id=base_message_id + index,
                    dry_run=args.dry_run,
                )
            except ConfigurationError:
                raise
            except AppError as exc:
                failures.append(f"{spec.symbol}: {exc}")
                print(f"failed {spec.symbol}: {exc}", file=sys.stderr)
            if not args.dry_run and index < len(specs) - 1:
                await asyncio.sleep(BATCH_PAUSE_SECONDS)
    finally:
        await trading.gateway.close()

    if failures:
        summary = "; ".join(failures)
        msg = f"{len(failures)} of {len(specs)} signals failed: {summary}"
        raise AppError(msg)


def main(argv: list[str] | None = None) -> None:
    """CLI entrypoint: ``python -m app.tools.simulate_signal``."""
    try:
        asyncio.run(run(argv))
    except ConfigurationError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
    except AppError as exc:
        print(f"Application error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    except KeyboardInterrupt:
        raise SystemExit(0) from None


if __name__ == "__main__":
    main()
