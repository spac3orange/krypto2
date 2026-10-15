"""Load and update runtime trading config. Secrets stay in the environment."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from app.core.config import Settings
from app.core.errors import ConfigurationError
from app.domain.trading.enums import OrderSizingPrice, TradingMode
from app.domain.trading.runtime_config import RuntimeConfigStore, RuntimeTradingConfig

_TRUE = {"1", "true", "yes", "on", "вкл", "да"}
_FALSE = {"0", "false", "no", "off", "выкл", "нет"}

_BOOL_KEYS = frozenset(
    {
        "TAKE_PROFIT_ENABLED",
        "STOP_LOSS_ENABLED",
        "EXECUTE_EDITED_MESSAGES",
        "REACT_DUMP",
        "REACT_PUMP",
        "REACT_SHORT",
        "ORDERS_ENABLED",
    }
)

_KEYS = (
    "TRADING_MODE",
    "BYBIT_LEVERAGE",
    "TRADE_MARGIN_PCT",
    "ORDER_SIZING_PRICE",
    "TAKE_PROFIT_ENABLED",
    "TAKE_PROFIT_PCT",
    "STOP_LOSS_ENABLED",
    "STOP_LOSS_PCT",
    "MAX_SIGNAL_AGE_SECONDS",
    "EXECUTE_EDITED_MESSAGES",
    "REACT_DUMP",
    "REACT_PUMP",
    "REACT_SHORT",
    "ORDERS_ENABLED",
)


def defaults_from_settings(settings: Settings) -> dict[str, str]:
    """Env snapshot used to seed an empty database."""
    stop = "" if settings.stop_loss_pct is None else str(settings.stop_loss_pct)
    return {
        "TRADING_MODE": settings.trading_mode.value,
        "BYBIT_LEVERAGE": str(settings.bybit_leverage),
        "TRADE_MARGIN_PCT": str(settings.trade_margin_pct),
        "ORDER_SIZING_PRICE": settings.order_sizing_price.value,
        "TAKE_PROFIT_ENABLED": _bool_text(settings.take_profit_enabled),
        "TAKE_PROFIT_PCT": str(settings.take_profit_pct),
        "STOP_LOSS_ENABLED": _bool_text(settings.stop_loss_enabled),
        "STOP_LOSS_PCT": stop,
        "MAX_SIGNAL_AGE_SECONDS": str(settings.max_signal_age_seconds),
        "EXECUTE_EDITED_MESSAGES": _bool_text(settings.execute_edited_messages),
        "REACT_DUMP": _bool_text(settings.react_dump),
        "REACT_PUMP": _bool_text(settings.react_pump),
        "REACT_SHORT": _bool_text(settings.react_short),
        "ORDERS_ENABLED": _bool_text(settings.orders_enabled),
    }


def _bool_text(value: bool) -> str:
    return "true" if value else "false"


_BOOL_HINT = "true | false | 1 | 0 | on | off | вкл | выкл | да | нет"


def _parse_bool(raw: str) -> bool:
    key = raw.strip().lower()
    if key in _TRUE:
        return True
    if key in _FALSE:
        return False
    msg = f"Допустимо: {_BOOL_HINT}"
    raise ConfigurationError(msg)


def _parse_decimal(raw: str, *, label: str) -> Decimal:
    try:
        return Decimal(raw.strip())
    except InvalidOperation as exc:
        msg = f"{label}: нужно число, получено {raw!r}"
        raise ConfigurationError(msg) from exc


def parse_stored_config(values: dict[str, str]) -> RuntimeTradingConfig:
    """Build a config object from stored strings."""
    missing = [key for key in _KEYS if key not in values]
    if missing:
        msg = f"runtime config missing keys: {', '.join(missing)}"
        raise ConfigurationError(msg)
    mode_raw = values["TRADING_MODE"].strip().lower()
    if mode_raw == "testnet":
        msg = "TRADING_MODE=testnet is not supported; use demo"
        raise ConfigurationError(msg)
    try:
        mode = TradingMode(mode_raw)
    except ValueError as exc:
        msg = "TRADING_MODE must be disabled, demo, or mainnet"
        raise ConfigurationError(msg) from exc
    try:
        sizing = OrderSizingPrice(values["ORDER_SIZING_PRICE"].strip())
    except ValueError as exc:
        msg = "ORDER_SIZING_PRICE must be lastPrice or markPrice"
        raise ConfigurationError(msg) from exc
    stop_raw = values["STOP_LOSS_PCT"].strip()
    stop_pct = None if stop_raw == "" else _parse_decimal(stop_raw, label="STOP_LOSS_PCT")
    age_raw = values["MAX_SIGNAL_AGE_SECONDS"].strip()
    if not age_raw.isdigit():
        msg = "MAX_SIGNAL_AGE_SECONDS must be a positive integer"
        raise ConfigurationError(msg)
    return RuntimeTradingConfig(
        trading_mode=mode,
        bybit_leverage=_parse_decimal(values["BYBIT_LEVERAGE"], label="BYBIT_LEVERAGE"),
        trade_margin_pct=_parse_decimal(values["TRADE_MARGIN_PCT"], label="TRADE_MARGIN_PCT"),
        order_sizing_price=sizing,
        take_profit_enabled=_parse_bool(values["TAKE_PROFIT_ENABLED"]),
        take_profit_pct=_parse_decimal(values["TAKE_PROFIT_PCT"], label="TAKE_PROFIT_PCT"),
        stop_loss_enabled=_parse_bool(values["STOP_LOSS_ENABLED"]),
        stop_loss_pct=stop_pct,
        max_signal_age_seconds=int(age_raw),
        execute_edited_messages=_parse_bool(values["EXECUTE_EDITED_MESSAGES"]),
        react_dump=_parse_bool(values["REACT_DUMP"]),
        react_pump=_parse_bool(values["REACT_PUMP"]),
        react_short=_parse_bool(values["REACT_SHORT"]),
        orders_enabled=_parse_bool(values["ORDERS_ENABLED"]),
    )


class SettingsRuntimeConfig:
    """Immutable view of env settings. Used when no database is wired."""

    def __init__(self, settings: Settings) -> None:
        self._config = parse_stored_config(defaults_from_settings(settings))

    def get(self) -> RuntimeTradingConfig:
        return self._config


class RuntimeConfigService:
    """Seed, read, and validate updates against the SQLite store."""

    def __init__(self, settings: Settings, store: RuntimeConfigStore) -> None:
        self._settings = settings
        self._store = store
        self._defaults = defaults_from_settings(settings)

    def seed(self) -> RuntimeTradingConfig:
        """Fill any missing keys from the environment. Existing DB values win."""
        current = self._store.get_all()
        missing = {key: value for key, value in self._defaults.items() if key not in current}
        if missing:
            self._store.put_many(missing)
        return self.get()

    def get(self) -> RuntimeTradingConfig:
        merged = dict(self._defaults)
        merged.update(self._store.get_all())
        return self._validate(parse_stored_config(merged))

    def set_field(self, key: str, raw_value: str) -> RuntimeTradingConfig:
        """Validate one field and persist it."""
        normalized = key.strip().upper()
        if normalized not in _KEYS:
            known = ", ".join(_KEYS)
            msg = f"Неизвестный ключ {key!r}. Доступны: {known}"
            raise ConfigurationError(msg)
        current = self.get()
        stored = _apply_field(current, normalized, raw_value, allow_mainnet=self._allow_mainnet)
        self._store.put_many({normalized: stored})
        return self.get()

    @property
    def _allow_mainnet(self) -> bool:
        return self._settings.allow_mainnet_trading

    def _validate(self, config: RuntimeTradingConfig) -> RuntimeTradingConfig:
        if config.trading_mode is TradingMode.MAINNET and not self._allow_mainnet:
            msg = "TRADING_MODE=mainnet requires ALLOW_MAINNET_TRADING=true"
            raise ConfigurationError(msg)
        _check_ranges(config)
        return config


def _apply_field(
    current: RuntimeTradingConfig,
    key: str,
    raw_value: str,
    *,
    allow_mainnet: bool,
) -> str:
    """Return the canonical stored string for one field."""
    if key == "TRADING_MODE":
        mode = raw_value.strip().lower()
        if mode == "testnet":
            msg = "TRADING_MODE=testnet не поддерживается. Допустимо: disabled | demo | mainnet"
            raise ConfigurationError(msg)
        if mode == TradingMode.MAINNET.value and not allow_mainnet:
            msg = "TRADING_MODE=mainnet сейчас запрещён. Допустимо: disabled | demo"
            raise ConfigurationError(msg)
        try:
            return TradingMode(mode).value
        except ValueError as exc:
            msg = "Допустимо: disabled | demo | mainnet"
            raise ConfigurationError(msg) from exc
    if key == "BYBIT_LEVERAGE":
        value = _parse_decimal(raw_value, label=key)
        if value < Decimal("1"):
            msg = "Допустимо: число ≥ 1"
            raise ConfigurationError(msg)
        return str(value)
    if key == "TRADE_MARGIN_PCT":
        value = _parse_decimal(raw_value, label=key)
        if not (Decimal("0") < value <= Decimal("100")):
            msg = "Допустимо: число от 0 до 100, не включая 0"
            raise ConfigurationError(msg)
        return str(value)
    if key == "ORDER_SIZING_PRICE":
        try:
            return OrderSizingPrice(raw_value.strip()).value
        except ValueError as exc:
            msg = "Допустимо: lastPrice | markPrice"
            raise ConfigurationError(msg) from exc
    if key in _BOOL_KEYS:
        try:
            enabled = _parse_bool(raw_value)
        except ConfigurationError as exc:
            msg = f"Допустимо: {_BOOL_HINT}"
            raise ConfigurationError(msg) from exc
        if key == "STOP_LOSS_ENABLED" and enabled and current.stop_loss_pct is None:
            msg = "Сначала задай STOP_LOSS_PCT, потом включай стоп"
            raise ConfigurationError(msg)
        if key == "TAKE_PROFIT_ENABLED" and enabled and current.take_profit_pct <= 0:
            msg = "Сначала задай TAKE_PROFIT_PCT > 0"
            raise ConfigurationError(msg)
        return _bool_text(enabled)
    if key == "TAKE_PROFIT_PCT":
        value = _parse_decimal(raw_value, label=key)
        if value <= 0:
            msg = "Допустимо: число > 0"
            raise ConfigurationError(msg)
        return str(value)
    if key == "STOP_LOSS_PCT":
        value = _parse_decimal(raw_value, label=key)
        if value <= 0:
            msg = "Допустимо: число > 0"
            raise ConfigurationError(msg)
        return str(value)
    if key == "MAX_SIGNAL_AGE_SECONDS":
        raw = raw_value.strip()
        if not raw.isdigit() or int(raw) <= 0:
            msg = "Допустимо: целое число ≥ 1"
            raise ConfigurationError(msg)
        return str(int(raw))
    msg = f"Неизвестный ключ {key!r}"
    raise ConfigurationError(msg)


def _check_ranges(config: RuntimeTradingConfig) -> None:
    if config.bybit_leverage < Decimal("1"):
        msg = "BYBIT_LEVERAGE must be >= 1"
        raise ConfigurationError(msg)
    if not (Decimal("0") < config.trade_margin_pct <= Decimal("100")):
        msg = "TRADE_MARGIN_PCT must satisfy 0 < value <= 100"
        raise ConfigurationError(msg)
    if config.take_profit_enabled and config.take_profit_pct <= 0:
        msg = "TAKE_PROFIT_PCT must be > 0"
        raise ConfigurationError(msg)
    if config.stop_loss_enabled and (config.stop_loss_pct is None or config.stop_loss_pct <= 0):
        msg = "STOP_LOSS_PCT must be > 0 when stop loss is enabled"
        raise ConfigurationError(msg)
    if config.max_signal_age_seconds <= 0:
        msg = "MAX_SIGNAL_AGE_SECONDS must be > 0"
        raise ConfigurationError(msg)
