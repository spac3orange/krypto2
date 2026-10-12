"""Centralized typed configuration."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import Field, ValidationInfo, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from app.core.errors import ConfigurationError
from app.domain.trading.enums import (
    ExistingPositionPolicy,
    OrderSizingPrice,
    TradingMode,
)


def _to_decimal(value: object) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if value is None or value == "":
        msg = "numeric value is required"
        raise ValueError(msg)
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        msg = f"invalid decimal: {value!r}"
        raise ValueError(msg) from exc


class Settings(BaseSettings):
    """Application settings loaded from environment / `.env`."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: Literal["development", "staging", "production"] = Field(
        default="development",
        alias="APP_ENV",
    )
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO",
        alias="LOG_LEVEL",
    )
    log_telegram_message_text: bool = Field(
        default=False,
        alias="LOG_TELEGRAM_MESSAGE_TEXT",
    )

    telegram_api_id: int = Field(alias="TELEGRAM_API_ID")
    telegram_api_hash: str = Field(alias="TELEGRAM_API_HASH")
    telegram_session_path: Path = Field(
        default=Path("data/telegram/user"),
        alias="TELEGRAM_SESSION_PATH",
    )
    telegram_source_chat_id: int | None = Field(
        default=None,
        alias="TELEGRAM_SOURCE_CHAT_ID",
    )
    telegram_source_username: str | None = Field(
        default=None,
        alias="TELEGRAM_SOURCE_USERNAME",
    )
    telegram_catch_up_enabled: bool = Field(
        default=True,
        alias="TELEGRAM_CATCH_UP_ENABLED",
    )
    telegram_ready_marker_path: Path = Field(
        default=Path("data/telegram/.ready"),
        alias="TELEGRAM_READY_MARKER_PATH",
    )
    proxy_url: str | None = Field(
        default=None,
        alias="PROXY_URL",
    )

    # --- Trading / Bybit ---
    trading_mode: TradingMode = Field(
        default=TradingMode.DISABLED,
        alias="TRADING_MODE",
    )
    allow_mainnet_trading: bool = Field(
        default=False,
        alias="ALLOW_MAINNET_TRADING",
    )
    bybit_api_key: str | None = Field(default=None, alias="BYBIT_API_KEY")
    bybit_api_secret: str | None = Field(default=None, alias="BYBIT_API_SECRET")
    bybit_category: Literal["linear"] = Field(default="linear", alias="BYBIT_CATEGORY")
    bybit_settle_coin: Literal["USDT"] = Field(default="USDT", alias="BYBIT_SETTLE_COIN")
    bybit_leverage: Decimal = Field(default=Decimal("5"), alias="BYBIT_LEVERAGE")
    bybit_expected_margin_mode: str | None = Field(
        default=None,
        alias="BYBIT_EXPECTED_MARGIN_MODE",
    )
    trade_margin_pct: Decimal = Field(default=Decimal("1.0"), alias="TRADE_MARGIN_PCT")
    order_sizing_price: OrderSizingPrice = Field(
        default=OrderSizingPrice.LAST_PRICE,
        alias="ORDER_SIZING_PRICE",
    )
    take_profit_enabled: bool = Field(default=True, alias="TAKE_PROFIT_ENABLED")
    take_profit_pct: Decimal = Field(default=Decimal("2.0"), alias="TAKE_PROFIT_PCT")
    take_profit_trigger_by: str = Field(
        default="LastPrice",
        alias="TAKE_PROFIT_TRIGGER_BY",
    )
    stop_loss_enabled: bool = Field(default=False, alias="STOP_LOSS_ENABLED")
    stop_loss_pct: Decimal | None = Field(default=None, alias="STOP_LOSS_PCT")
    max_signal_age_seconds: int = Field(default=30, alias="MAX_SIGNAL_AGE_SECONDS")
    execute_edited_messages: bool = Field(
        default=False,
        alias="EXECUTE_EDITED_MESSAGES",
    )
    existing_position_policy: ExistingPositionPolicy = Field(
        default=ExistingPositionPolicy.SKIP,
        alias="EXISTING_POSITION_POLICY",
    )
    execution_db_path: Path = Field(
        default=Path("data/trading/executions.sqlite3"),
        alias="EXECUTION_DB_PATH",
    )
    order_fill_timeout_sec: float = Field(
        default=30.0,
        alias="ORDER_FILL_TIMEOUT_SEC",
    )
    telegram_bot_token: str | None = Field(default=None, alias="TELEGRAM_BOT_TOKEN")
    telegram_bot_admin_ids: Annotated[frozenset[int], NoDecode] = Field(
        default_factory=frozenset,
        alias="TELEGRAM_BOT_ADMIN_IDS",
    )

    @field_validator(
        "log_telegram_message_text",
        "telegram_catch_up_enabled",
        "allow_mainnet_trading",
        "take_profit_enabled",
        "stop_loss_enabled",
        "execute_edited_messages",
        mode="before",
    )
    @classmethod
    def _blank_bool_uses_default(cls, value: object, info: ValidationInfo) -> object:
        """Blank env values (``KEY=``) keep the field default."""
        if isinstance(value, str) and value.strip() == "":
            field_name = info.field_name
            if field_name is None:
                return value
            return cls.model_fields[field_name].default
        return value

    @field_validator("telegram_api_hash")
    @classmethod
    def _api_hash_non_empty(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            msg = "TELEGRAM_API_HASH must be a non-empty string"
            raise ValueError(msg)
        return cleaned

    @field_validator("telegram_source_chat_id", mode="before")
    @classmethod
    def _empty_chat_id_to_none(cls, value: object) -> object:
        if value == "" or value is None:
            return None
        return value

    @field_validator("telegram_source_username", mode="before")
    @classmethod
    def _normalize_username(cls, value: object) -> str | None:
        if value is None or value == "":
            return None
        cleaned = str(value).strip().lstrip("@")
        return cleaned or None

    @field_validator("telegram_bot_token", mode="before")
    @classmethod
    def _empty_bot_token_to_none(cls, value: object) -> str | None:
        if value is None or value == "":
            return None
        cleaned = str(value).strip()
        return cleaned or None

    @field_validator("telegram_bot_admin_ids", mode="before")
    @classmethod
    def _parse_admin_ids(cls, value: object) -> frozenset[int]:
        if value is None or value == "":
            return frozenset()
        if isinstance(value, frozenset):
            return value
        parts = str(value).replace(";", ",").split(",")
        ids: set[int] = set()
        for part in parts:
            cleaned = part.strip()
            if not cleaned:
                continue
            if not cleaned.lstrip("-").isdigit():
                msg = f"TELEGRAM_BOT_ADMIN_IDS has a non-integer id: {cleaned!r}"
                raise ValueError(msg)
            ids.add(int(cleaned))
        return frozenset(ids)

    @field_validator("proxy_url", "bybit_api_key", "bybit_api_secret", mode="before")
    @classmethod
    def _empty_str_to_none(cls, value: object) -> str | None:
        if value is None or value == "":
            return None
        cleaned = str(value).strip()
        return cleaned or None

    @field_validator("bybit_expected_margin_mode", mode="before")
    @classmethod
    def _empty_margin_mode_to_none(cls, value: object) -> str | None:
        if value is None or value == "":
            return None
        return str(value).strip() or None

    @field_validator(
        "bybit_leverage",
        "trade_margin_pct",
        "take_profit_pct",
        mode="before",
    )
    @classmethod
    def _parse_required_decimal(cls, value: object) -> Decimal:
        return _to_decimal(value)

    @field_validator("stop_loss_pct", mode="before")
    @classmethod
    def _parse_optional_decimal(cls, value: object) -> Decimal | None:
        if value is None or value == "":
            return None
        return _to_decimal(value)

    @field_validator("trading_mode", mode="before")
    @classmethod
    def _parse_trading_mode(cls, value: object) -> object:
        if value is None or value == "":
            return TradingMode.DISABLED
        if isinstance(value, TradingMode):
            return value
        raw = str(value).strip().lower()
        if raw == "testnet":
            msg = "TRADING_MODE=testnet is not supported; use demo (Bybit Demo Trading)"
            raise ValueError(msg)
        try:
            return TradingMode(raw)
        except ValueError as exc:
            msg = f"Unknown TRADING_MODE={value!r}; expected disabled|demo|mainnet"
            raise ValueError(msg) from exc

    @model_validator(mode="after")
    def _validate_trading_and_source(self) -> Self:
        has_chat_id = self.telegram_source_chat_id is not None
        has_username = self.telegram_source_username is not None
        if has_chat_id == has_username:
            msg = "Exactly one of TELEGRAM_SOURCE_CHAT_ID or TELEGRAM_SOURCE_USERNAME must be set"
            raise ValueError(msg)

        if not (Decimal("0") < self.trade_margin_pct <= Decimal("100")):
            msg = "TRADE_MARGIN_PCT must satisfy 0 < value <= 100"
            raise ValueError(msg)
        if self.bybit_leverage < Decimal("1"):
            msg = "BYBIT_LEVERAGE must be >= 1"
            raise ValueError(msg)
        if self.max_signal_age_seconds <= 0:
            msg = "MAX_SIGNAL_AGE_SECONDS must be > 0"
            raise ValueError(msg)
        if self.order_fill_timeout_sec <= 0:
            msg = "ORDER_FILL_TIMEOUT_SEC must be > 0"
            raise ValueError(msg)
        if self.take_profit_enabled and self.take_profit_pct <= 0:
            msg = "TAKE_PROFIT_PCT must be > 0 when TAKE_PROFIT_ENABLED=true"
            raise ValueError(msg)
        if self.stop_loss_enabled and (self.stop_loss_pct is None or self.stop_loss_pct <= 0):
            msg = "STOP_LOSS_PCT must be > 0 when STOP_LOSS_ENABLED=true"
            raise ValueError(msg)

        if self.trading_mode is TradingMode.MAINNET and not self.allow_mainnet_trading:
            msg = "TRADING_MODE=mainnet requires ALLOW_MAINNET_TRADING=true (mainnet kill-switch)"
            raise ValueError(msg)

        if self.trading_mode is not TradingMode.DISABLED and (
            not self.bybit_api_key or not self.bybit_api_secret
        ):
            msg = "BYBIT_API_KEY and BYBIT_API_SECRET are required when trading is enabled"
            raise ValueError(msg)
        if self.telegram_bot_token and not self.telegram_bot_admin_ids:
            msg = "TELEGRAM_BOT_ADMIN_IDS is required when TELEGRAM_BOT_TOKEN is set"
            raise ValueError(msg)

        return self

    @property
    def telegram_source(self) -> int | str:
        """Configured source entity (chat id or username)."""
        if self.telegram_source_chat_id is not None:
            return self.telegram_source_chat_id
        if self.telegram_source_username is not None:
            return self.telegram_source_username
        msg = "Telegram source is not configured"
        raise ConfigurationError(msg)

    @property
    def trading_enabled(self) -> bool:
        return self.trading_mode is not TradingMode.DISABLED

    @property
    def bybit_demo(self) -> bool:
        """True only for Bybit Demo Trading (api-demo), never testnet."""
        return self.trading_mode is TradingMode.DEMO


def load_settings() -> Settings:
    """Load and validate settings; raise ConfigurationError on failure."""
    try:
        return Settings()  # type: ignore[call-arg]
    except Exception as exc:  # pydantic ValidationError and others
        raise ConfigurationError(str(exc)) from exc


class AuthSettings(BaseSettings):
    """Minimal settings required for interactive Telegram authorization."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO",
        alias="LOG_LEVEL",
    )
    telegram_api_id: int = Field(alias="TELEGRAM_API_ID")
    telegram_api_hash: str = Field(alias="TELEGRAM_API_HASH")
    telegram_session_path: Path = Field(
        default=Path("data/telegram/user"),
        alias="TELEGRAM_SESSION_PATH",
    )
    proxy_url: str | None = Field(
        default=None,
        alias="PROXY_URL",
    )

    @field_validator("telegram_api_hash")
    @classmethod
    def _api_hash_non_empty(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            msg = "TELEGRAM_API_HASH must be a non-empty string"
            raise ValueError(msg)
        return cleaned

    @field_validator("proxy_url", mode="before")
    @classmethod
    def _empty_proxy_to_none(cls, value: object) -> str | None:
        if value is None or value == "":
            return None
        cleaned = str(value).strip()
        return cleaned or None


def load_auth_settings() -> AuthSettings:
    """Load settings needed for the auth bootstrap CLI."""
    try:
        return AuthSettings()  # type: ignore[call-arg]
    except Exception as exc:
        raise ConfigurationError(str(exc)) from exc
