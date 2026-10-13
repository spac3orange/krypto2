"""Runtime config store and validation (no network)."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
from app.application.notifications.format import (
    config_help_text,
    config_start_text,
    format_order_notice,
    format_runtime_config,
    format_signal_notice,
)
from app.application.trading.runtime_config_service import RuntimeConfigService
from app.core.config import Settings
from app.core.errors import ConfigurationError
from app.domain.notifications.models import OrderNotice, OrderUpdateKind, SignalNotice
from app.domain.trading.enums import TradingMode
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
    with pytest.raises(ConfigurationError, match="ALLOW_MAINNET_TRADING"):
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


def test_start_is_short_and_help_is_detailed(monkeypatch: pytest.MonkeyPatch) -> None:
    service = RuntimeConfigService(_settings(monkeypatch), MemoryConfigStore())
    service.seed()
    start = config_start_text(service.get())
    help_text = config_help_text()
    assert "<b><u>Текущие настройки</u></b>" in start
    assert "<b>Режим торговли:</b> <code>demo</code>" in start
    assert "<b>Плечо:</b> <code>5</code>" in start
    assert "<b>Стоп, % от цены входа:</b> <code>3%</code>" in start
    assert "Как работать" not in start
    assert "Лонг закрывается" not in start
    assert "sqlite" not in start.lower()
    assert "<b><u>Как работать</u></b>" in help_text
    assert "python -m app" in help_text
    assert "<b>Плечо</b>" in help_text
    assert "<i>Пример:</i> /set BYBIT_LEVERAGE 5" in help_text
    assert "sqlite" not in help_text.lower()
    assert "База:" not in help_text


def test_config_view_describes_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    service = RuntimeConfigService(_settings(monkeypatch), MemoryConfigStore())
    service.seed()
    text = format_runtime_config(service.get())
    assert "<b><u>TRADING_MODE</u></b> = <code>demo</code>" in text
    assert "<b>Режим торговли</b>" in text
    assert "База:" not in text
    assert "sqlite" not in text.lower()


def test_notices_do_not_include_secrets() -> None:
    secret = "super-secret-bybit-key"
    signal = format_signal_notice(
        SignalNotice(
            symbol="BTC",
            signal_type="DUMP",
            action="BUY",
            timeframe="10m",
            change_percent="-5",
            price_from="1",
            price_to="0.95",
        )
    )
    order = format_order_notice(
        OrderNotice(symbol="BTC", kind=OrderUpdateKind.SUBMITTED, side="Buy", qty="0.01")
    )
    assert "BTC" in signal
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
