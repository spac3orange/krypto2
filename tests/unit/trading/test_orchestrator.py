"""Orchestrator integration tests with FakeTradingGateway."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from app.application.trading.orchestrator import TradingSignalOrchestrator
from app.application.trading.order_link_id import build_order_link_id
from app.core.config import Settings
from app.domain.telegram.enums import TelegramEventType
from app.domain.telegram.models import TelegramMessageEvent
from app.domain.trading.enums import (
    ExecutionStatus,
    OrderSide,
    PositionDirection,
    TradeAction,
    TradingSignalType,
)
from app.domain.trading.models import ParsedTradingSignal, PositionSnapshot
from app.infrastructure.persistence.sqlite_execution_store import SqliteExecutionStore

from tests.unit.trading.fakes import FakeTradingGateway


def make_settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, **env: str) -> Settings:
    defaults = {
        "TELEGRAM_API_ID": "1",
        "TELEGRAM_API_HASH": "hashhashhash",
        "TELEGRAM_SOURCE_USERNAME": "bot",
        "TRADING_MODE": "demo",
        "BYBIT_API_KEY": "key",
        "BYBIT_API_SECRET": "secret",
        "TRADE_MARGIN_PCT": "1",
        "BYBIT_LEVERAGE": "5",
        "TAKE_PROFIT_ENABLED": "true",
        "TAKE_PROFIT_PCT": "2",
        "MAX_SIGNAL_AGE_SECONDS": "60",
        "EXECUTE_EDITED_MESSAGES": "false",
        "ALLOW_MAINNET_TRADING": "false",
        "EXECUTION_DB_PATH": str(tmp_path / "exec.sqlite3"),
        "ORDER_FILL_TIMEOUT_SEC": "5",
    }
    defaults.update(env)
    for key, value in defaults.items():
        monkeypatch.setenv(key, value)
    return Settings()  # type: ignore[call-arg]


def _event(
    *,
    event_id: str = "telegram:1:1:new",
    event_type: TelegramEventType = TelegramEventType.NEW_MESSAGE,
    age_seconds: int = 5,
) -> TelegramMessageEvent:
    now = datetime.now(UTC)
    return TelegramMessageEvent(
        event_id=event_id,
        event_type=event_type,
        chat_id=1,
        message_id=1,
        sender_id=1,
        sender_username="bot",
        chat_username=None,
        text="signal",
        date=now - timedelta(seconds=age_seconds),
        edit_date=None,
        received_at=now,
        has_media=False,
        reply_to_message_id=None,
    )


def _signal(*, action: TradeAction = TradeAction.BUY, symbol: str = "SAGA") -> ParsedTradingSignal:
    return ParsedTradingSignal(
        exchange="BYBIT",
        timeframe="10m",
        symbol=symbol,
        signal_type=(
            TradingSignalType.DUMP if action is TradeAction.BUY else TradingSignalType.SHORT
        ),
        action=action,
        change_percent=Decimal("10"),
        price_from=Decimal("1"),
        price_to=Decimal("1.1"),
        signal_24h_count=1,
    )


@pytest.mark.asyncio
async def test_dump_opens_long(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    settings = make_settings(monkeypatch, tmp_path)
    gw = FakeTradingGateway()
    gw.add_linear_usdt("SAGAUSDT", last_price="0.50", min_notional="5")
    store = SqliteExecutionStore(settings.execution_db_path)
    orch = TradingSignalOrchestrator(settings, gateway=gw, store=store)

    await orch.handle(_event(), _signal(action=TradeAction.BUY))

    assert len(gw.placed) == 1
    assert gw.placed[0]["side"] is OrderSide.BUY
    assert gw.placed[0]["qty"] == Decimal("10")
    assert gw.trading_stops
    tp = gw.trading_stops[0][1].take_profit_price
    assert tp == Decimal("0.5100")  # 0.50 * 1.02


@pytest.mark.asyncio
async def test_pump_opens_short(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    settings = make_settings(monkeypatch, tmp_path)
    gw = FakeTradingGateway()
    gw.add_linear_usdt("SAGAUSDT", last_price="0.50", min_notional="5")
    store = SqliteExecutionStore(settings.execution_db_path)
    orch = TradingSignalOrchestrator(settings, gateway=gw, store=store)

    await orch.handle(_event(event_id="telegram:1:2:new"), _signal(action=TradeAction.SELL))

    assert gw.placed[0]["side"] is OrderSide.SELL
    tp = gw.trading_stops[0][1].take_profit_price
    assert tp == Decimal("0.4900")


@pytest.mark.asyncio
async def test_orders_disabled_skips(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    settings = make_settings(monkeypatch, tmp_path, ORDERS_ENABLED="false")
    gw = FakeTradingGateway()
    gw.add_linear_usdt("SAGAUSDT")
    orch = TradingSignalOrchestrator(
        settings, gateway=gw, store=SqliteExecutionStore(settings.execution_db_path)
    )
    await orch.handle(_event(event_id="telegram:1:orders-off:new"), _signal())
    assert gw.placed == []


@pytest.mark.asyncio
async def test_order_open_delay_waits(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    settings = make_settings(monkeypatch, tmp_path, ORDER_OPEN_DELAY_SEC="3")
    gw = FakeTradingGateway()
    gw.add_linear_usdt("SAGAUSDT", last_price="0.50", min_notional="5")
    orch = TradingSignalOrchestrator(
        settings, gateway=gw, store=SqliteExecutionStore(settings.execution_db_path)
    )
    slept: list[float] = []

    async def _fake_sleep(seconds: float) -> None:
        slept.append(seconds)

    monkeypatch.setattr("app.application.trading.orchestrator.asyncio.sleep", _fake_sleep)
    await orch.handle(_event(event_id="telegram:1:delay:new"), _signal())
    assert slept == [3.0]
    assert len(gw.placed) == 1


@pytest.mark.asyncio
async def test_react_dump_off_skips_dump(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    settings = make_settings(monkeypatch, tmp_path, REACT_DUMP="false")
    gw = FakeTradingGateway()
    gw.add_linear_usdt("SAGAUSDT")
    orch = TradingSignalOrchestrator(
        settings, gateway=gw, store=SqliteExecutionStore(settings.execution_db_path)
    )
    await orch.handle(_event(event_id="telegram:1:dump-off:new"), _signal())
    assert gw.placed == []


@pytest.mark.asyncio
async def test_stale_signal_skipped(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    settings = make_settings(monkeypatch, tmp_path, MAX_SIGNAL_AGE_SECONDS="5")
    gw = FakeTradingGateway()
    gw.add_linear_usdt("SAGAUSDT")
    orch = TradingSignalOrchestrator(
        settings, gateway=gw, store=SqliteExecutionStore(settings.execution_db_path)
    )
    await orch.handle(_event(age_seconds=60), _signal())
    assert gw.placed == []


@pytest.mark.asyncio
async def test_edited_message_skipped(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    settings = make_settings(monkeypatch, tmp_path)
    gw = FakeTradingGateway()
    gw.add_linear_usdt("SAGAUSDT")
    orch = TradingSignalOrchestrator(
        settings, gateway=gw, store=SqliteExecutionStore(settings.execution_db_path)
    )
    await orch.handle(
        _event(event_type=TelegramEventType.MESSAGE_EDITED),
        _signal(),
    )
    assert gw.placed == []


@pytest.mark.asyncio
async def test_instrument_not_found(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    settings = make_settings(monkeypatch, tmp_path)
    gw = FakeTradingGateway()
    orch = TradingSignalOrchestrator(
        settings, gateway=gw, store=SqliteExecutionStore(settings.execution_db_path)
    )
    await orch.handle(_event(), _signal(symbol="NOSUCH"))
    assert gw.placed == []


@pytest.mark.asyncio
async def test_existing_position_skip(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    settings = make_settings(monkeypatch, tmp_path)
    gw = FakeTradingGateway()
    gw.add_linear_usdt("SAGAUSDT")
    gw.positions["SAGAUSDT"] = PositionSnapshot(
        symbol="SAGAUSDT",
        size=Decimal("3"),
        side="Buy",
        avg_price=Decimal("0.5"),
        leverage=Decimal("5"),
    )
    orch = TradingSignalOrchestrator(
        settings, gateway=gw, store=SqliteExecutionStore(settings.execution_db_path)
    )
    await orch.handle(_event(), _signal())
    assert gw.placed == []


@pytest.mark.asyncio
async def test_durable_duplicate_does_not_resubmit(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    settings = make_settings(monkeypatch, tmp_path)
    gw = FakeTradingGateway()
    gw.add_linear_usdt("SAGAUSDT", last_price="0.50")
    store = SqliteExecutionStore(settings.execution_db_path)
    orch = TradingSignalOrchestrator(settings, gateway=gw, store=store)
    event = _event(event_id="telegram:1:99:new")

    await orch.handle(event, _signal())
    assert len(gw.placed) == 1

    await orch.handle(event, _signal())
    assert len(gw.placed) == 1
    rec = store.get_by_event_id(event.event_id)
    assert rec is not None
    assert rec.status in {
        ExecutionStatus.COMPLETED,
        ExecutionStatus.RECONCILED,
        ExecutionStatus.FILLED,
        ExecutionStatus.TP_SET,
    }


@pytest.mark.asyncio
async def test_uncertain_create_reconciles_without_second_order(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    settings = make_settings(monkeypatch, tmp_path)
    gw = FakeTradingGateway()
    gw.add_linear_usdt("SAGAUSDT", last_price="0.50")
    gw.place_raises_uncertain = True
    store = SqliteExecutionStore(settings.execution_db_path)
    orch = TradingSignalOrchestrator(settings, gateway=gw, store=store)

    await orch.handle(_event(event_id="telegram:1:77:new"), _signal())
    assert len(gw.placed) == 1  # one attempt only


def test_deterministic_order_link_id() -> None:
    a = build_order_link_id("telegram:1:1:new")
    b = build_order_link_id("telegram:1:1:new")
    c = build_order_link_id("telegram:1:2:new")
    assert a == b
    assert a != c
    assert a.startswith("k2-")
    assert len(a) <= 36


@pytest.mark.asyncio
async def test_map_actions() -> None:
    assert TradingSignalOrchestrator._map_side(TradeAction.BUY) == (
        OrderSide.BUY,
        PositionDirection.LONG,
    )
    assert TradingSignalOrchestrator._map_side(TradeAction.SELL) == (
        OrderSide.SELL,
        PositionDirection.SHORT,
    )
