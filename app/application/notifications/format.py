"""Operator-bot messages. Config and help use Telegram HTML."""

from __future__ import annotations

import html
from dataclasses import dataclass

from app.domain.notifications.models import OrderNotice, OrderUpdateKind, SignalNotice
from app.domain.trading.models import AccountSnapshot, OpenOrderSnapshot, PositionSnapshot
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
    allowed: str


_BOOL_ALLOWED = "true | false | 1 | 0 | on | off | вкл | выкл | да | нет"

_FIELD_HELP: dict[str, _FieldHelp] = {
    "TRADING_MODE": _FieldHelp(
        "Режим торговли",
        "disabled — только уведомления, без сделок. "
        "demo — сделки на демо-счёте. "
        "mainnet — сделки на реальном счёте (если разрешено отдельно).",
        "/set TRADING_MODE demo",
        "disabled | demo | mainnet",
    ),
    "BYBIT_LEVERAGE": _FieldHelp(
        "Плечо",
        "Плечо для новых сделок. На уже открытую позицию не действует.",
        "/set BYBIT_LEVERAGE 5",
        "число ≥ 1 (например 5)",
    ),
    "TRADE_MARGIN_PCT": _FieldHelp(
        "Маржа, % свободных USDT",
        "Какая доля Available (свободных USDT) идёт в маржу одной сделки. "
        "Объём позиции ≈ маржа × плечо. Equity на размер не влияет.",
        "/set TRADE_MARGIN_PCT 1",
        "число от 0 до 100, не включая 0 (например 1 или 0.5)",
    ),
    "ORDER_SIZING_PRICE": _FieldHelp(
        "Цена для расчёта объёма",
        "lastPrice — цена последней сделки. markPrice — маркировочная цена.",
        "/set ORDER_SIZING_PRICE lastPrice",
        "lastPrice | markPrice",
    ),
    "TAKE_PROFIT_ENABLED": _FieldHelp(
        "Тейк-профит",
        "Включить или выключить тейк-профит.",
        "/set TAKE_PROFIT_ENABLED true",
        _BOOL_ALLOWED,
    ),
    "TAKE_PROFIT_PCT": _FieldHelp(
        "Тейк, % от цены входа",
        "На сколько процентов от цены входа ставить тейк. "
        "Лонг — выше входа, шорт — ниже.",
        "/set TAKE_PROFIT_PCT 2",
        "число > 0 (например 2)",
    ),
    "STOP_LOSS_ENABLED": _FieldHelp(
        "Стоп-лосс",
        "Включить или выключить стоп-лосс. Сначала задай STOP_LOSS_PCT.",
        "/set STOP_LOSS_ENABLED true",
        _BOOL_ALLOWED,
    ),
    "STOP_LOSS_PCT": _FieldHelp(
        "Стоп, % от цены входа",
        "На сколько процентов от цены входа ставить стоп. "
        "Лонг — ниже входа, шорт — выше.",
        "/set STOP_LOSS_PCT 3",
        "число > 0 (например 3)",
    ),
    "MAX_SIGNAL_AGE_SECONDS": _FieldHelp(
        "Максимальный возраст сигнала, секунды",
        "Сигнал старше этого времени сделку не открывает.",
        "/set MAX_SIGNAL_AGE_SECONDS 30",
        "целое число ≥ 1 (например 30)",
    ),
    "ORDER_OPEN_DELAY_SEC": _FieldHelp(
        "Задержка перед ордером, секунды",
        "Сколько ждать после сигнала перед отправкой ордера на биржу. 0 — сразу.",
        "/set ORDER_OPEN_DELAY_SEC 5",
        "целое число ≥ 0 (например 0 или 5)",
    ),
    "EXECUTE_EDITED_MESSAGES": _FieldHelp(
        "Торговать правки сообщений",
        "Нет — правка сигнала новую сделку не открывает. Да — правка тоже торгуется.",
        "/set EXECUTE_EDITED_MESSAGES false",
        _BOOL_ALLOWED,
    ),
    "REACT_DUMP": _FieldHelp(
        "Реакция на Dump",
        "Вкл — реагируем на 🔻 Dump (открываем лонг). Выкл — такие сигналы пропускаем.",
        "/set REACT_DUMP true",
        _BOOL_ALLOWED,
    ),
    "REACT_PUMP": _FieldHelp(
        "Реакция на 🟢 Pump",
        "Вкл — реагируем на 🟢 Pump (открываем шорт). Выкл — такие сигналы пропускаем.",
        "/set REACT_PUMP true",
        _BOOL_ALLOWED,
    ),
    "REACT_SHORT": _FieldHelp(
        "Реакция на 🔴 Pump",
        "Вкл — реагируем на 🔴 Pump (открываем шорт). Выкл — такие сигналы пропускаем.",
        "/set REACT_SHORT true",
        _BOOL_ALLOWED,
    ),
    "ORDERS_ENABLED": _FieldHelp(
        "Размещение ордеров",
        "Вкл — после сигнала ставим сделки. Выкл — сигнал показываем, ордера не отправляем.",
        "/set ORDERS_ENABLED true",
        _BOOL_ALLOWED,
    ),
}


def _on_off(enabled: bool) -> str:
    return "вкл" if enabled else "выкл"


def _config_rows(config: RuntimeTradingConfig) -> tuple[tuple[str, str], ...]:
    stop_pct = "" if config.stop_loss_pct is None else str(config.stop_loss_pct)
    return (
        ("TRADING_MODE", config.trading_mode.value),
        ("ORDERS_ENABLED", _on_off(config.orders_enabled)),
        ("REACT_DUMP", _on_off(config.react_dump)),
        ("REACT_PUMP", _on_off(config.react_pump)),
        ("REACT_SHORT", _on_off(config.react_short)),
        ("BYBIT_LEVERAGE", str(config.bybit_leverage)),
        ("TRADE_MARGIN_PCT", str(config.trade_margin_pct)),
        ("ORDER_SIZING_PRICE", config.order_sizing_price.value),
        ("TAKE_PROFIT_ENABLED", _on_off(config.take_profit_enabled)),
        ("TAKE_PROFIT_PCT", str(config.take_profit_pct)),
        ("STOP_LOSS_ENABLED", _on_off(config.stop_loss_enabled)),
        ("STOP_LOSS_PCT", stop_pct or "не задан"),
        ("MAX_SIGNAL_AGE_SECONDS", str(config.max_signal_age_seconds)),
        ("ORDER_OPEN_DELAY_SEC", str(config.order_open_delay_sec)),
        ("EXECUTE_EDITED_MESSAGES", _on_off(config.execute_edited_messages)),
    )


def format_runtime_config(config: RuntimeTradingConfig) -> str:
    """Current editable settings with allowed values for each key."""
    lines = [
        "<b><u>Настройки</u></b>",
        "Менять только через <code>/set КЛЮЧ ЗНАЧЕНИЕ</code>.",
        "Если значение не из списка — настройка не применится.",
        "",
    ]
    for key, value in _config_rows(config):
        field = _FIELD_HELP[key]
        lines.append(f"<b><u>{html.escape(key)}</u></b> = <code>{html.escape(value)}</code>")
        lines.append(f"<b>{html.escape(field.title)}</b>")
        lines.append(html.escape(field.details))
        lines.append(f"<b>Допустимо:</b> <code>{html.escape(field.allowed)}</code>")
        lines.append(f"<i>Пример:</i> <code>{html.escape(field.example)}</code>")
        lines.append("")
    lines.append("<b>Подробности:</b> /help")
    return "\n".join(lines).rstrip()


def format_balance(snapshot: AccountSnapshot, *, trading_mode: str) -> str:
    """Operator-facing balance snapshot from Bybit API."""
    return (
        "<b><u>Баланс Bybit</u></b>\n"
        f"Режим: <code>{html.escape(trading_mode)}</code>\n"
        f"Equity: <code>{html.escape(str(snapshot.total_equity))}</code>\n"
        f"Available: <code>{html.escape(str(snapshot.total_available_balance))}</code>\n"
        f"Margin mode: <code>{html.escape(snapshot.margin_mode or '—')}</code>\n"
        f"Account: <code>{html.escape(snapshot.account_type)}</code>"
    )


def format_open_exposure(
    *,
    trading_mode: str,
    positions: list[PositionSnapshot],
    orders: list[OpenOrderSnapshot],
) -> str:
    """Open positions + working orders (why Available may be 0)."""
    lines = [
        "<b><u>Открыто на Bybit</u></b>",
        f"Режим: <code>{html.escape(trading_mode)}</code>",
        "",
        f"<b>Позиции</b> ({len(positions)}):",
    ]
    if not positions:
        lines.append("<i>нет</i>")
    else:
        for pos in positions[:30]:
            side = html.escape(pos.side or "—")
            avg = html.escape(str(pos.avg_price) if pos.avg_price is not None else "—")
            lev = html.escape(str(pos.leverage) if pos.leverage is not None else "—")
            im = html.escape(str(pos.position_im) if pos.position_im is not None else "—")
            pnl = html.escape(
                str(pos.unrealised_pnl) if pos.unrealised_pnl is not None else "—"
            )
            lines.append(
                f"{format_symbol_link(pos.symbol)} {side} "
                f"size=<code>{html.escape(str(pos.size))}</code> "
                f"avg=<code>{avg}</code> lev=<code>{lev}</code>\n"
                f"  margin(IM)=<code>{im}</code> uPnL=<code>{pnl}</code>"
            )
        if len(positions) > 30:
            lines.append(f"<i>… ещё {len(positions) - 30}</i>")

    lines.append("")
    lines.append(f"<b>Открытые ордера</b> ({len(orders)}):")
    if not orders:
        lines.append("<i>нет</i>")
    else:
        for order in orders[:30]:
            price = html.escape(str(order.price) if order.price is not None else "market")
            reduce = " reduceOnly" if order.reduce_only else ""
            link = html.escape(order.order_link_id) if order.order_link_id else "—"
            lines.append(
                f"{format_symbol_link(order.symbol)} "
                f"{html.escape(order.side)} {html.escape(order.order_type)} "
                f"qty=<code>{html.escape(str(order.qty))}</code> "
                f"left=<code>{html.escape(str(order.leaves_qty))}</code> "
                f"px=<code>{price}</code> "
                f"{html.escape(order.order_status)}{reduce}\n"
                f"  link=<code>{link}</code>"
            )
        if len(orders) > 30:
            lines.append(f"<i>… ещё {len(orders) - 30}</i>")

    return "\n".join(lines)


def format_set_usage() -> str:
    """Help for incomplete /set."""
    lines = [
        "<b>Формат:</b> <code>/set КЛЮЧ ЗНАЧЕНИЕ</code>",
        "",
        "<b>Доступные ключи и значения:</b>",
    ]
    for key, field in _FIELD_HELP.items():
        lines.append(f"<code>{html.escape(key)}</code> — {html.escape(field.allowed)}")
    lines.append("")
    lines.append("Текущие значения: /config")
    return "\n".join(lines)


def format_set_error(key: str, message: str) -> str:
    """Validation error with allowed values for the key when known."""
    normalized = key.strip().upper()
    lines = [f"<b>Ошибка:</b> {html.escape(message)}"]
    field = _FIELD_HELP.get(normalized)
    if field is not None:
        lines.append(f"<b>Ключ:</b> <code>{html.escape(normalized)}</code>")
        lines.append(f"<b>Допустимо:</b> <code>{html.escape(field.allowed)}</code>")
        lines.append(f"<i>Пример:</i> <code>{html.escape(field.example)}</code>")
    else:
        lines.append("<b>Доступные ключи:</b>")
        lines.append(", ".join(f"<code>{html.escape(name)}</code>" for name in _FIELD_HELP))
    return "\n".join(lines)


def config_start_text(config: RuntimeTradingConfig) -> str:
    """Short /start screen: commands and current values."""
    lines = [
        "<b><u>Команды</u></b>",
        "/config — настройки с описанием",
        "/help — реакция на сигналы и описание настроек",
        "/set КЛЮЧ ЗНАЧЕНИЕ — изменить настройку",
        "/get_balance — баланс Bybit (equity / available)",
        "",
        "<b><u>Текущие настройки</u></b>",
    ]
    for key, value in _config_rows(config):
        title = html.escape(_FIELD_HELP[key].title)
        lines.append(f"<b>{title}:</b> <code>{html.escape(value)}</code>")
    return "\n".join(lines)


def config_help_text() -> str:
    """Signal reaction guide and setting descriptions."""
    lines = [
        "<b><u>Сигналы @pump_screener_bot</u></b>",
        "Сюда приходят копии сигналов и статусы сделок.",
        "",
        "🔻 <b>Dump</b> — открываем <b>лонг</b> (покупка).",
        "🟢 / 🔴 <b>Pump</b> — всегда открываем <b>шорт</b> (продажа), "
        "цвет смайлика не важен.",
        "",
        "Реакцию можно выключить отдельно: "
        "<code>REACT_DUMP</code>, <code>REACT_PUMP</code> (🟢), "
        "<code>REACT_SHORT</code> (🔴).",
        "Размещение ордеров целиком: <code>ORDERS_ENABLED</code>.",
        "Пауза перед ордером: <code>ORDER_OPEN_DELAY_SEC</code>.",
        "",
        "Размер сделки считается от свободных USDT (Available), маржи и плеча. "
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
        "/get_balance — баланс счёта через Bybit API (equity и available)",
        "",
        "<b><u>Настройки</u></b>",
        "",
    ]
    for key, field in _FIELD_HELP.items():
        title = html.escape(field.title)
        lines.append(f"<b><u>{html.escape(key)}</u></b> — <b>{title}</b>")
        lines.append(html.escape(field.details))
        lines.append(f"<b>Допустимо:</b> <code>{html.escape(field.allowed)}</code>")
        lines.append(f"<i>Пример:</i> <code>{html.escape(field.example)}</code>")
        lines.append("")
    return "\n".join(lines).rstrip()
