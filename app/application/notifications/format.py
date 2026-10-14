"""Operator-bot messages. Config and help use Telegram HTML."""

from __future__ import annotations

import html
from dataclasses import dataclass

from app.domain.notifications.models import OrderNotice, OrderUpdateKind, SignalNotice
from app.domain.trading.runtime_config import RuntimeTradingConfig

_KIND_TITLE = {
    OrderUpdateKind.SUBMITTED: "Ордер отправлен",
    OrderUpdateKind.FILLED: "Ордер исполнен",
    OrderUpdateKind.SKIPPED: "Ордер не отправлен",
    OrderUpdateKind.REJECTED: "Ордер отклонён",
    OrderUpdateKind.FAILED: "Ошибка ордера",
}

_BYBIT_USDT_TRADE_URL = "https://www.bybit.com/trade/usdt/{symbol}"


def bybit_usdt_trade_url(symbol: str) -> str:
    """Bybit USDT perpetual trade page for a ticker (``BTR`` → ``BTRUSDT``)."""
    raw = symbol.strip().upper()
    pair = raw if raw.endswith("USDT") else f"{raw}USDT"
    return _BYBIT_USDT_TRADE_URL.format(symbol=pair)


def format_symbol_link(symbol: str) -> str:
    """HTML link to the Bybit trade page; visible text is the raw ticker."""
    label = html.escape(symbol.strip().upper() or symbol)
    href = html.escape(bybit_usdt_trade_url(symbol), quote=True)
    return f'<a href="{href}">{label}</a>'


def format_signal_notice(notice: SignalNotice) -> str:
    """Duplicate of a captured signal (Telegram HTML)."""
    return (
        "<b>Сигнал</b>\n"
        f"{html.escape(notice.signal_type)} {format_symbol_link(notice.symbol)} "
        f"{html.escape(notice.timeframe)}\n"
        f"{html.escape(notice.action)}  {html.escape(notice.change_percent)}%\n"
        f"{html.escape(notice.price_from)} → {html.escape(notice.price_to)}"
    )


def format_order_notice(notice: OrderNotice) -> str:
    """Status of a sent or skipped order (Telegram HTML)."""
    lines = [
        f"<b>{html.escape(_KIND_TITLE[notice.kind])}</b>",
        format_symbol_link(notice.symbol),
    ]
    if notice.side:
        lines.append(f"сторона: {html.escape(notice.side)}")
    if notice.qty:
        lines.append(f"qty: {html.escape(notice.qty)}")
    if notice.avg_price:
        lines.append(f"цена: {html.escape(notice.avg_price)}")
    if notice.take_profit:
        lines.append(f"TP: {html.escape(notice.take_profit)}")
    if notice.stop_loss:
        lines.append(f"SL: {html.escape(notice.stop_loss)}")
    if notice.reason:
        lines.append(f"причина: {html.escape(notice.reason)}")
    return "\n".join(lines)


@dataclass(frozen=True, slots=True)
class _FieldHelp:
    title: str
    details: str
    example: str


_FIELD_HELP: dict[str, _FieldHelp] = {
    "TRADING_MODE": _FieldHelp(
        "Режим торговли",
        "disabled — только уведомления, без сделок. "
        "demo — сделки на демо-счёте. "
        "mainnet — сделки на реальном счёте (если разрешено отдельно).",
        "/set TRADING_MODE demo",
    ),
    "BYBIT_LEVERAGE": _FieldHelp(
        "Плечо",
        "Плечо для новых сделок. На уже открытую позицию не действует.",
        "/set BYBIT_LEVERAGE 5",
    ),
    "TRADE_MARGIN_PCT": _FieldHelp(
        "Маржа, % депозита",
        "Какая доля депозита идёт в маржу одной сделки. "
        "Объём позиции ≈ маржа × плечо.",
        "/set TRADE_MARGIN_PCT 1",
    ),
    "ORDER_SIZING_PRICE": _FieldHelp(
        "Цена для расчёта объёма",
        "lastPrice — цена последней сделки. markPrice — маркировочная цена.",
        "/set ORDER_SIZING_PRICE lastPrice",
    ),
    "TAKE_PROFIT_ENABLED": _FieldHelp(
        "Тейк-профит",
        "Включить или выключить тейк-профит.",
        "/set TAKE_PROFIT_ENABLED true",
    ),
    "TAKE_PROFIT_PCT": _FieldHelp(
        "Тейк, % от цены входа",
        "На сколько процентов от цены входа ставить тейк. "
        "Лонг — выше входа, шорт — ниже.",
        "/set TAKE_PROFIT_PCT 2",
    ),
    "STOP_LOSS_ENABLED": _FieldHelp(
        "Стоп-лосс",
        "Включить или выключить стоп-лосс.",
        "/set STOP_LOSS_ENABLED true",
    ),
    "STOP_LOSS_PCT": _FieldHelp(
        "Стоп, % от цены входа",
        "На сколько процентов от цены входа ставить стоп. "
        "Лонг — ниже входа, шорт — выше.",
        "/set STOP_LOSS_PCT 3",
    ),
    "MAX_SIGNAL_AGE_SECONDS": _FieldHelp(
        "Максимальный возраст сигнала, секунды",
        "Сигнал старше этого времени сделку не открывает.",
        "/set MAX_SIGNAL_AGE_SECONDS 30",
    ),
    "EXECUTE_EDITED_MESSAGES": _FieldHelp(
        "Торговать правки сообщений",
        "Нет — правка сигнала новую сделку не открывает. Да — правка тоже торгуется.",
        "/set EXECUTE_EDITED_MESSAGES false",
    ),
    "REACT_DUMP": _FieldHelp(
        "Реакция на Dump",
        "Вкл — реагируем на 🔻 Dump (открываем лонг). Выкл — такие сигналы пропускаем.",
        "/set REACT_DUMP true",
    ),
    "REACT_PUMP": _FieldHelp(
        "Реакция на Pump (лонг)",
        "Вкл — реагируем на 🟢 Pump (открываем лонг). Выкл — такие сигналы пропускаем.",
        "/set REACT_PUMP true",
    ),
    "REACT_SHORT": _FieldHelp(
        "Реакция на Short",
        "Вкл — реагируем на 🔴 Pump / Short (открываем шорт). Выкл — такие сигналы пропускаем.",
        "/set REACT_SHORT true",
    ),
    "ORDERS_ENABLED": _FieldHelp(
        "Размещение ордеров",
        "Вкл — после сигнала ставим сделки. Выкл — сигнал показываем, ордера не отправляем.",
        "/set ORDERS_ENABLED true",
    ),
}


def _on_off(enabled: bool) -> str:
    return "вкл" if enabled else "выкл"


def _config_rows(config: RuntimeTradingConfig) -> tuple[tuple[str, str], ...]:
    stop = "выкл" if not config.stop_loss_enabled else f"{config.stop_loss_pct}%"
    take = "выкл" if not config.take_profit_enabled else f"{config.take_profit_pct}%"
    edited = "да" if config.execute_edited_messages else "нет"
    return (
        ("TRADING_MODE", config.trading_mode.value),
        ("ORDERS_ENABLED", _on_off(config.orders_enabled)),
        ("REACT_DUMP", _on_off(config.react_dump)),
        ("REACT_PUMP", _on_off(config.react_pump)),
        ("REACT_SHORT", _on_off(config.react_short)),
        ("BYBIT_LEVERAGE", str(config.bybit_leverage)),
        ("TRADE_MARGIN_PCT", f"{config.trade_margin_pct}%"),
        ("ORDER_SIZING_PRICE", config.order_sizing_price.value),
        ("TAKE_PROFIT", take),
        ("STOP_LOSS", stop),
        ("MAX_SIGNAL_AGE_SECONDS", f"{config.max_signal_age_seconds} с"),
        ("EXECUTE_EDITED_MESSAGES", edited),
    )


def format_runtime_config(config: RuntimeTradingConfig) -> str:
    """Current editable settings with a short Russian caption for each value."""
    lines = ["<b><u>Настройки</u></b>", ""]
    for key, value in _config_rows(config):
        field = _FIELD_HELP[_help_key(key)]
        lines.append(f"<b><u>{html.escape(key)}</u></b> = <code>{html.escape(value)}</code>")
        lines.append(f"<b>{html.escape(field.title)}</b>")
        lines.append(html.escape(field.details))
        lines.append("")
    lines.append("<b>Изменить:</b> /set КЛЮЧ ЗНАЧЕНИЕ")
    lines.append("<b>Подробности:</b> /help")
    return "\n".join(lines).rstrip()


def config_start_text(config: RuntimeTradingConfig) -> str:
    """Short /start screen: commands and current values."""
    lines = [
        "<b><u>Команды</u></b>",
        "/config — настройки с описанием",
        "/help — реакция на сигналы и описание настроек",
        "/set КЛЮЧ ЗНАЧЕНИЕ — изменить настройку",
        "",
        "<b><u>Текущие настройки</u></b>",
    ]
    for key, value in _config_rows(config):
        title = html.escape(_FIELD_HELP[_help_key(key)].title)
        lines.append(f"<b>{title}:</b> <code>{html.escape(value)}</code>")
    return "\n".join(lines)


def config_help_text() -> str:
    """Signal reaction guide and setting descriptions."""
    lines = [
        "<b><u>Сигналы @pump_screener_bot</u></b>",
        "Сюда приходят копии сигналов и статусы сделок.",
        "",
        "🔻 <b>Dump</b> — открываем <b>лонг</b> (покупка).",
        "🟢 <b>Pump</b> — открываем <b>лонг</b> (как «Лонг» в скринере).",
        "🔴 <b>Pump / Short</b> — открываем <b>шорт</b> (продажа).",
        "",
        "Реакцию на каждый тип можно выключить: "
        "<code>REACT_DUMP</code>, <code>REACT_PUMP</code>, <code>REACT_SHORT</code>.",
        "Размещение ордеров целиком: <code>ORDERS_ENABLED</code>.",
        "",
        "Размер сделки считается от депозита, маржи и плеча. "
        "Цены и процент из сообщения на объём не влияют.",
        "Если по монете уже есть позиция — новый сигнал пропускаем.",
        "Старые сигналы и правки сообщений по умолчанию не торгуем.",
        "После входа ставятся тейк и стоп от фактической цены входа.",
        "Изменения настроек действуют на следующий сигнал.",
        "",
        "<b><u>Команды</u></b>",
        "/config — текущие значения",
        "/start — короткий экран",
        "/set КЛЮЧ ЗНАЧЕНИЕ — изменить настройку",
        "",
        "<b><u>Настройки</u></b>",
        "",
    ]
    for key, field in _FIELD_HELP.items():
        title = html.escape(field.title)
        lines.append(f"<b><u>{html.escape(key)}</u></b> — <b>{title}</b>")
        lines.append(html.escape(field.details))
        lines.append(f"<i>Пример:</i> {html.escape(field.example)}")
        lines.append("")
    return "\n".join(lines).rstrip()


def _help_key(display_key: str) -> str:
    if display_key == "TAKE_PROFIT":
        return "TAKE_PROFIT_PCT"
    if display_key == "STOP_LOSS":
        return "STOP_LOSS_PCT"
    return display_key
