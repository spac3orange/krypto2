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


def format_signal_notice(notice: SignalNotice) -> str:
    """Duplicate of a captured signal."""
    return (
        "Сигнал\n"
        f"{notice.signal_type} {notice.symbol} {notice.timeframe}\n"
        f"{notice.action}  {notice.change_percent}%\n"
        f"{notice.price_from} → {notice.price_to}"
    )


def format_order_notice(notice: OrderNotice) -> str:
    """Status of a sent or skipped order."""
    lines = [_KIND_TITLE[notice.kind], notice.symbol]
    if notice.side:
        lines.append(f"сторона: {notice.side}")
    if notice.qty:
        lines.append(f"qty: {notice.qty}")
    if notice.avg_price:
        lines.append(f"цена: {notice.avg_price}")
    if notice.take_profit:
        lines.append(f"TP: {notice.take_profit}")
    if notice.stop_loss:
        lines.append(f"SL: {notice.stop_loss}")
    if notice.reason:
        lines.append(f"причина: {notice.reason}")
    return "\n".join(lines)


@dataclass(frozen=True, slots=True)
class _FieldHelp:
    title: str
    details: str
    example: str


_FIELD_HELP: dict[str, _FieldHelp] = {
    "TRADING_MODE": _FieldHelp(
        "Режим торговли",
        "disabled — сигналы приходят, ордера не открываются. "
        "demo — сделки на Bybit Demo Trading. "
        "mainnet из бота недоступен, пока в .env не включён ALLOW_MAINNET_TRADING.",
        "/set TRADING_MODE demo",
    ),
    "BYBIT_LEVERAGE": _FieldHelp(
        "Плечо",
        "Плечо для новых позиций. На уже открытую позицию не действует.",
        "/set BYBIT_LEVERAGE 5",
    ),
    "TRADE_MARGIN_PCT": _FieldHelp(
        "Маржа, % депозита",
        "Какая доля депозита уходит в маржу одной сделки. "
        "Это не объём позиции: объём ≈ маржа × плечо.",
        "/set TRADE_MARGIN_PCT 1",
    ),
    "ORDER_SIZING_PRICE": _FieldHelp(
        "Цена для расчёта объёма",
        "lastPrice — цена последней сделки. markPrice — маркировочная цена.",
        "/set ORDER_SIZING_PRICE lastPrice",
    ),
    "TAKE_PROFIT_ENABLED": _FieldHelp(
        "Тейк-профит",
        "true — ставить тейк. false — не ставить. Значения: true или false.",
        "/set TAKE_PROFIT_ENABLED true",
    ),
    "TAKE_PROFIT_PCT": _FieldHelp(
        "Тейк, % от цены входа",
        "Лонг закрывается выше входа, шорт — ниже. Считается от фактической цены входа.",
        "/set TAKE_PROFIT_PCT 2",
    ),
    "STOP_LOSS_ENABLED": _FieldHelp(
        "Стоп-лосс",
        "true — ставить стоп. false — не ставить. Сначала задай STOP_LOSS_PCT.",
        "/set STOP_LOSS_ENABLED true",
    ),
    "STOP_LOSS_PCT": _FieldHelp(
        "Стоп, % от цены входа",
        "Лонг закрывается ниже входа, шорт — выше. Считается от фактической цены входа.",
        "/set STOP_LOSS_PCT 3",
    ),
    "MAX_SIGNAL_AGE_SECONDS": _FieldHelp(
        "Максимальный возраст сигнала, секунды",
        "Сообщение старше этого порога не открывает сделку.",
        "/set MAX_SIGNAL_AGE_SECONDS 30",
    ),
    "EXECUTE_EDITED_MESSAGES": _FieldHelp(
        "Торговать правки сообщений",
        "false — изменённое сообщение не создаёт новый ордер. true — правка тоже торгуется.",
        "/set EXECUTE_EDITED_MESSAGES false",
    ),
}


def format_runtime_config(config: RuntimeTradingConfig) -> str:
    """Current editable settings with a short Russian caption for each value."""
    stop = "выкл" if not config.stop_loss_enabled else f"{config.stop_loss_pct}%"
    take = "выкл" if not config.take_profit_enabled else f"{config.take_profit_pct}%"
    edited = "да" if config.execute_edited_messages else "нет"
    rows = (
        ("TRADING_MODE", config.trading_mode.value),
        ("BYBIT_LEVERAGE", str(config.bybit_leverage)),
        ("TRADE_MARGIN_PCT", str(config.trade_margin_pct)),
        ("ORDER_SIZING_PRICE", config.order_sizing_price.value),
        ("TAKE_PROFIT", take),
        ("STOP_LOSS", stop),
        ("MAX_SIGNAL_AGE_SECONDS", str(config.max_signal_age_seconds)),
        ("EXECUTE_EDITED_MESSAGES", edited),
    )
    lines = ["<b><u>Настройки</u></b>", ""]
    for key, value in rows:
        field = _FIELD_HELP[_help_key(key)]
        lines.append(f"<b><u>{html.escape(key)}</u></b> = <code>{html.escape(value)}</code>")
        lines.append(f"<b>{html.escape(field.title)}</b>")
        lines.append(html.escape(field.details))
        lines.append("")
    lines.append("<b>Изменить:</b> /set КЛЮЧ ЗНАЧЕНИЕ")
    lines.append("<b>Подробности:</b> /help")
    return "\n".join(lines).rstrip()


def config_start_text() -> str:
    """Short command list for /start."""
    return (
        "Команды:\n"
        "/config — текущие настройки\n"
        "/help — как работать и что значит каждый ключ\n"
        "/set КЛЮЧ ЗНАЧЕНИЕ — изменить настройку\n"
        "\n"
        "Ключи:\n"
        "TRADING_MODE (disabled|demo)\n"
        "BYBIT_LEVERAGE\n"
        "TRADE_MARGIN_PCT\n"
        "ORDER_SIZING_PRICE (lastPrice|markPrice)\n"
        "TAKE_PROFIT_ENABLED (true|false)\n"
        "TAKE_PROFIT_PCT\n"
        "STOP_LOSS_ENABLED (true|false)\n"
        "STOP_LOSS_PCT\n"
        "MAX_SIGNAL_AGE_SECONDS\n"
        "EXECUTE_EDITED_MESSAGES (true|false)\n"
        "\n"
        "Ключи биржи и токен бота здесь не меняются."
    )


def config_help_text() -> str:
    """How to use the bot and what each setting means."""
    lines = [
        "<b><u>Как работать</u></b>",
        "Бот запускается вместе с программой командой python -m app.",
        "Сюда приходят копии сигналов и статусы ордеров.",
        "Настройки из бота сохраняются и действуют на следующий сигнал.",
        "Ключи биржи и токен бота меняются только в файле .env.",
        "",
        "<b><u>Команды</u></b>",
        "/config — текущие значения",
        "/start — короткий список команд",
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
