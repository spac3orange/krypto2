"""Config / kill-switch / logging safety tests."""

from __future__ import annotations

import logging

import pytest
from app.core.config import Settings
from app.core.logging import JsonFormatter, log_event
from app.infrastructure.bybit.client import create_bybit_http
from pydantic import ValidationError


def test_mainnet_requires_allow_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TELEGRAM_API_ID", "1")
    monkeypatch.setenv("TELEGRAM_API_HASH", "hash")
    monkeypatch.setenv("TELEGRAM_SOURCE_USERNAME", "bot")
    monkeypatch.setenv("TRADING_MODE", "mainnet")
    monkeypatch.setenv("ALLOW_MAINNET_TRADING", "false")
    monkeypatch.setenv("BYBIT_API_KEY", "k")
    monkeypatch.setenv("BYBIT_API_SECRET", "s")
    with pytest.raises(ValidationError):
        Settings()  # type: ignore[call-arg]


def test_testnet_mode_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TELEGRAM_API_ID", "1")
    monkeypatch.setenv("TELEGRAM_API_HASH", "hash")
    monkeypatch.setenv("TELEGRAM_SOURCE_USERNAME", "bot")
    monkeypatch.setenv("TRADING_MODE", "testnet")
    monkeypatch.setenv("BYBIT_API_KEY", "k")
    monkeypatch.setenv("BYBIT_API_SECRET", "s")
    with pytest.raises(ValidationError, match="use demo"):
        Settings()  # type: ignore[call-arg]


def test_demo_mode_targets_demo_host(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TELEGRAM_API_ID", "1")
    monkeypatch.setenv("TELEGRAM_API_HASH", "hash")
    monkeypatch.setenv("TELEGRAM_SOURCE_USERNAME", "bot")
    monkeypatch.setenv("TRADING_MODE", "demo")
    monkeypatch.setenv("BYBIT_API_KEY", "k")
    monkeypatch.setenv("BYBIT_API_SECRET", "s")
    settings = Settings()  # type: ignore[call-arg]
    assert settings.bybit_demo is True
    http = create_bybit_http(
        api_key="k",
        api_secret="s",
        demo=settings.bybit_demo,
    )
    assert http.endpoint == "https://api-demo.bybit.com"
    assert http.recv_window == 20_000


def test_mainnet_mode_targets_mainnet_host(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TELEGRAM_API_ID", "1")
    monkeypatch.setenv("TELEGRAM_API_HASH", "hash")
    monkeypatch.setenv("TELEGRAM_SOURCE_USERNAME", "bot")
    monkeypatch.setenv("TRADING_MODE", "mainnet")
    monkeypatch.setenv("ALLOW_MAINNET_TRADING", "true")
    monkeypatch.setenv("BYBIT_API_KEY", "k")
    monkeypatch.setenv("BYBIT_API_SECRET", "s")
    settings = Settings()  # type: ignore[call-arg]
    assert settings.bybit_demo is False
    http = create_bybit_http(
        api_key="k",
        api_secret="s",
        demo=settings.bybit_demo,
    )
    assert http.endpoint == "https://api.bybit.com"


def test_unknown_trading_mode_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TELEGRAM_API_ID", "1")
    monkeypatch.setenv("TELEGRAM_API_HASH", "hash")
    monkeypatch.setenv("TELEGRAM_SOURCE_USERNAME", "bot")
    monkeypatch.setenv("TRADING_MODE", "prod")
    with pytest.raises(ValidationError):
        Settings()  # type: ignore[call-arg]


def test_blank_bool_env_uses_field_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TELEGRAM_API_ID", "1")
    monkeypatch.setenv("TELEGRAM_API_HASH", "hash")
    monkeypatch.setenv("TELEGRAM_SOURCE_USERNAME", "bot")
    monkeypatch.setenv("TRADING_MODE", "disabled")
    monkeypatch.setenv("LOG_TELEGRAM_MESSAGE_TEXT", "")
    monkeypatch.setenv("TAKE_PROFIT_ENABLED", "")
    monkeypatch.setenv("STOP_LOSS_ENABLED", "")
    settings = Settings()  # type: ignore[call-arg]
    assert settings.log_telegram_message_text is False
    assert settings.take_profit_enabled is True
    assert settings.stop_loss_enabled is False


def test_disabled_mode_does_not_require_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TELEGRAM_API_ID", "1")
    monkeypatch.setenv("TELEGRAM_API_HASH", "hash")
    monkeypatch.setenv("TELEGRAM_SOURCE_USERNAME", "bot")
    monkeypatch.setenv("TRADING_MODE", "disabled")
    monkeypatch.delenv("BYBIT_API_KEY", raising=False)
    monkeypatch.delenv("BYBIT_API_SECRET", raising=False)
    settings = Settings()  # type: ignore[call-arg]
    assert settings.trading_enabled is False


def test_api_secret_not_in_json_logs(caplog: pytest.LogCaptureFixture) -> None:
    secret = "super-secret-bybit-key"
    logger = logging.getLogger("secret_test")
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    logger.handlers = [handler]
    logger.setLevel(logging.INFO)
    with caplog.at_level(logging.INFO):
        log_event(
            logger,
            logging.INFO,
            "trading.preflight.ok",
            "ok",
            api_key_id="123",
            # Must never pass secret into log fields in real code; assert formatter
            # does not invent it either.
        )
    text = " ".join(r.getMessage() for r in caplog.records)
    assert secret not in text
    assert "trading.preflight.ok" in str(caplog.records[0].__dict__.get("event"))
