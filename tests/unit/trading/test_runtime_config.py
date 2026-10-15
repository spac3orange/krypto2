"""Runtime config store and validation (no network)."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
from app.application.notifications.format import (
    bybit_usdt_trade_url,
    config_help_text,
    config_start_text,
    format_balance,
    format_open_exposure,
    format_order_notice,
    format_runtime_config,
    format_signal_notice,
)
from app.application.trading.runtime_config_service import RuntimeConfigService
from app.core.config import Settings
from app.core.errors import ConfigurationError
from app.domain.notifications.models import OrderNotice, OrderUpdateKind, SignalNotice
from app.domain.trading.enums import TradingMode
from app.domain.trading.models import AccountSnapshot, OpenOrderSnapshot, PositionSnapshot
from app.infrastructure.persistence.sqlite_runtime_config import SqliteRuntimeConfigStore


class MemoryConfigStore:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def get_all(self) -> dict[str, str]:
        return dict(self.values)

    def put_many(self, values: dict[str, str]) -> None:
        self.values.update(values)


def _settings(monkeypatch: pytest.MonkeyPatch, **env: str) -> Settings:
    base = {
        "TELEGRAM_API_ID": "1",
        "TELEGRAM_API_HASH": "hash",
        "TELEGRAM_SOURCE_USERNAME": "bot",
        "TRADING_MODE": "demo",
        "BYBIT_API_KEY": "k",
        "BYBIT_API_SECRET": "s",
        "BYBIT_LEVERAGE": "5",
        "TRADE_MARGIN_PCT": "1",
        "STOP_LOSS_ENABLED": "true",
        "STOP_LOSS_PCT": "3",
        "ALLOW_MAINNET_TRADING": "false",
    }
    base.update(env)
    for key, value in base.items():
        monkeypatch.setenv(key, value)
    return Settings()  # type: ignore[call-arg]


def test_seed_then_set_leverage_persists(monkeypatch: pytest.MonkeyPatch) -> None:
    service = RuntimeConfigService(_settings(monkeypatch), MemoryConfigStore())
    service.seed()
    updated = service.set_field("bybit_leverage", "7")
    assert updated.bybit_leverage == Decimal("7")
    assert service.get().bybit_leverage == Decimal("7")


def test_set_mainnet_rejected_without_kill_switch(monkeypatch: pytest.MonkeyPatch) -> None:
    service = RuntimeConfigService(_settings(monkeypatch), MemoryConfigStore())
    service.seed()
    with pytest.raises(ConfigurationError, match="mainnet|disabled | demo"):
        service.set_field("TRADING_MODE", "mainnet")
    assert service.get().trading_mode is TradingMode.DEMO


def test_set_stop_requires_percent(monkeypatch: pytest.MonkeyPatch) -> None:
    service = RuntimeConfigService(
        _settings(monkeypatch, STOP_LOSS_ENABLED="false", STOP_LOSS_PCT=""),
        MemoryConfigStore(),
    )
    service.seed()
    with pytest.raises(ConfigurationError, match="STOP_LOSS_PCT"):
        service.set_field("STOP_LOSS_ENABLED", "true")


def test_sqlite_config_roundtrip(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    store = SqliteRuntimeConfigStore(tmp_path / "trading.sqlite3")
    service = RuntimeConfigService(_settings(monkeypatch), store)
    service.seed()
    service.set_field("TRADE_MARGIN_PCT", "2.5")
    again = RuntimeConfigService(_settings(monkeypatch), store)
    assert again.get().trade_margin_pct == Decimal("2.5")


def test_format_balance_shows_equity_and_available() -> None:
    text = format_balance(
        AccountSnapshot(
            total_equity=Decimal("1000.5"),
            total_available_balance=Decimal("800.25"),
            margin_mode="REGULAR_MARGIN",
            unified_margin_status=3,
            account_type="UNIFIED",
        ),
        trading_mode="demo",
    )
    assert "Equity: <code>1000.5</code>" in text
    assert "Available: <code>800.25</code>" in text
    assert "Режим: <code>demo</code>" in text
    assert "TRADE_MARGIN_PCT" in text


def test_format_open_exposure_lists_positions_and_orders() -> None:
    text = format_open_exposure(
        trading_mode="demo",
        positions=[
            PositionSnapshot(
                symbol="BTCUSDT",
                size=Decimal("0.01"),
                side="Buy",
                avg_price=Decimal("50000"),
                leverage=Decimal("5"),
                position_im=Decimal("100"),
                unrealised_pnl=Decimal("1.5"),
            )
        ],
        orders=[
            OpenOrderSnapshot(
                symbol="ETHUSDT",
                side="Sell",
                order_type="Limit",
                qty=Decimal("1"),
                leaves_qty=Decimal("1"),
                price=Decimal("3000"),
                order_status="New",
                reduce_only=False,
                order_link_id="abc",
            )
        ],
    )
    assert "Позиции</b> (1)" in text
    assert "BTCUSDT" in text
    assert "margin(IM)=<code>100</code>" in text
    assert "Открытые ордера</b> (1)" in text
    assert "ETHUSDT" in text
    assert "Available=0" in text


def test_start_is_short_and_help_is_detailed(monkeypatch: pytest.MonkeyPatch) -> None:
    service = RuntimeConfigService(_settings(monkeypatch), MemoryConfigStore())
    service.seed()
    start = config_start_text(service.get())
    help_text = config_help_text()
    assert "<b><u>Текущие настройки</u></b>" in start
    assert "<b>Режим торговли:</b> <code>demo</code>" in start
    assert "<b>Плечо:</b> <code>5</code>" in start
    assert "<b>Стоп, % от цены входа:</b> <code>3</code>" in start
    assert "python -m app" not in start
    assert ".env" not in start
    assert "sqlite" not in start.lower()
    assert "<b><u>Сигналы @pump_screener_bot</u></b>" in help_text
    assert "Dump" in help_text and "лонг" in help_text
    assert "REACT_SHORT" in help_text
    assert "ORDERS_ENABLED" in help_text
    assert "/get_balance" in start
    assert "/get_balance" in help_text
    assert "/get_orders" in start
    assert "/get_orders" in help_text
    assert "<b>Реакция на Dump:</b> <code>вкл</code>" in start
    assert "python -m app" not in help_text
    assert ".env" not in help_text
    assert "ALLOW_MAINNET" not in help_text
    assert "<b>Плечо</b>" in help_text
    assert "Допустимо:" in help_text
    assert "<i>Пример:</i> <code>/set BYBIT_LEVERAGE 5</code>" in help_text
    assert "sqlite" not in help_text.lower()
    assert "База:" not in help_text


def test_config_view_describes_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    service = RuntimeConfigService(_settings(monkeypatch), MemoryConfigStore())
    service.seed()
    text = format_runtime_config(service.get())
    assert "<b><u>TRADING_MODE</u></b> = <code>demo</code>" in text
    assert "<b>Режим торговли</b>" in text
    assert "<b>Допустимо:</b> <code>disabled | demo | mainnet</code>" in text
    assert "<b>Допустимо:</b> <code>lastPrice | markPrice</code>" in text
    assert "База:" not in text
    assert "sqlite" not in text.lower()


def test_set_accepts_russian_bool(monkeypatch: pytest.MonkeyPatch) -> None:
    service = RuntimeConfigService(_settings(monkeypatch), MemoryConfigStore())
    service.seed()
    updated = service.set_field("ORDERS_ENABLED", "выкл")
    assert updated.orders_enabled is False
    updated = service.set_field("REACT_DUMP", "да")
    assert updated.react_dump is True


def test_set_rejects_bad_value_with_hint(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.application.notifications.format import format_set_error

    service = RuntimeConfigService(_settings(monkeypatch), MemoryConfigStore())
    service.seed()
    with pytest.raises(ConfigurationError, match="Допустимо"):
        service.set_field("TRADING_MODE", "paper")
    err = format_set_error("TRADING_MODE", "Допустимо: disabled | demo | mainnet")
    assert "disabled | demo | mainnet" in err
    assert "/set TRADING_MODE demo" in err


def test_bybit_trade_url_appends_usdt() -> None:
    assert bybit_usdt_trade_url("BTR") == "https://www.bybit.com/trade/usdt/BTRUSDT"
    assert bybit_usdt_trade_url("btcusdt") == "https://www.bybit.com/trade/usdt/BTCUSDT"


def test_notices_link_symbol_to_bybit() -> None:
    secret = "super-secret-bybit-key"
    signal = format_signal_notice(
        SignalNotice(
            symbol="BTR",
            signal_type="DUMP",
            action="BUY",
            timeframe="10m",
            change_percent="-15.08",
            price_from="0.05094",
            price_to="0.04326",
        )
    )
    order = format_order_notice(
        OrderNotice(symbol="BTR", kind=OrderUpdateKind.SUBMITTED, side="Buy", qty="0.01")
    )
    link = '<a href="https://www.bybit.com/trade/usdt/BTRUSDT">BTR</a>'
    assert link in signal
    assert link in order
    assert "Ордер отправлен" in order
    assert secret not in signal
    assert secret not in order


def test_bot_token_requires_admin_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TELEGRAM_API_ID", "1")
    monkeypatch.setenv("TELEGRAM_API_HASH", "hash")
    monkeypatch.setenv("TELEGRAM_SOURCE_USERNAME", "bot")
    monkeypatch.setenv("TRADING_MODE", "disabled")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:abc")
    monkeypatch.setenv("TELEGRAM_BOT_ADMIN_IDS", "")
    with pytest.raises(Exception, match="TELEGRAM_BOT_ADMIN_IDS"):
        Settings()  # type: ignore[call-arg]


def test_admin_ids_parsed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TELEGRAM_API_ID", "1")
    monkeypatch.setenv("TELEGRAM_API_HASH", "hash")
    monkeypatch.setenv("TELEGRAM_SOURCE_USERNAME", "bot")
    monkeypatch.setenv("TRADING_MODE", "disabled")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:abc")
    monkeypatch.setenv("TELEGRAM_BOT_ADMIN_IDS", "10, 20")
    settings = Settings()  # type: ignore[call-arg]
    assert settings.telegram_bot_admin_ids == frozenset({10, 20})
