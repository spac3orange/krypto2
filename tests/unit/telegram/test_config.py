"""Unit tests for configuration validation."""

from __future__ import annotations

import pytest
from app.core.config import Settings, load_settings
from app.core.errors import ConfigurationError
from pydantic import ValidationError


def _base_telegram_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Override process env + .env file values for isolated settings tests."""
    monkeypatch.setenv("TELEGRAM_API_ID", "12345")
    monkeypatch.setenv("TELEGRAM_API_HASH", "hashhash")
    monkeypatch.setenv("TELEGRAM_SOURCE_CHAT_ID", "")
    monkeypatch.setenv("TELEGRAM_SOURCE_USERNAME", "")


def test_settings_requires_exactly_one_source(monkeypatch: pytest.MonkeyPatch) -> None:
    _base_telegram_env(monkeypatch)

    with pytest.raises(ValidationError):
        Settings()  # type: ignore[call-arg]


def test_settings_rejects_both_sources(monkeypatch: pytest.MonkeyPatch) -> None:
    _base_telegram_env(monkeypatch)
    monkeypatch.setenv("TELEGRAM_SOURCE_CHAT_ID", "-1001")
    monkeypatch.setenv("TELEGRAM_SOURCE_USERNAME", "bot")

    with pytest.raises(ValidationError):
        Settings()  # type: ignore[call-arg]


def test_settings_accepts_chat_id(monkeypatch: pytest.MonkeyPatch) -> None:
    _base_telegram_env(monkeypatch)
    monkeypatch.setenv("TELEGRAM_SOURCE_CHAT_ID", "-1001")
    monkeypatch.setenv("TELEGRAM_SOURCE_USERNAME", "")

    settings = Settings()  # type: ignore[call-arg]
    assert settings.telegram_source == -1001


def test_settings_accepts_username_and_strips_at(monkeypatch: pytest.MonkeyPatch) -> None:
    _base_telegram_env(monkeypatch)
    monkeypatch.setenv("TELEGRAM_SOURCE_CHAT_ID", "")
    monkeypatch.setenv("TELEGRAM_SOURCE_USERNAME", "@signals_bot")

    settings = Settings()  # type: ignore[call-arg]
    assert settings.telegram_source == "signals_bot"


def test_load_settings_wraps_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TELEGRAM_API_ID", "")
    monkeypatch.setenv("TELEGRAM_API_HASH", "")
    monkeypatch.setenv("TELEGRAM_SOURCE_CHAT_ID", "")
    monkeypatch.setenv("TELEGRAM_SOURCE_USERNAME", "")

    with pytest.raises(ConfigurationError):
        load_settings()


def test_empty_source_strings_treated_as_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    _base_telegram_env(monkeypatch)

    with pytest.raises(ValidationError):
        Settings()  # type: ignore[call-arg]
