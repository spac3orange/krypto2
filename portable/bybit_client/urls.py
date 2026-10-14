"""Public Bybit website helpers."""

from __future__ import annotations

_BYBIT_USDT_TRADE_URL = "https://www.bybit.com/trade/usdt/{symbol}"


def usdt_perp_trade_url(symbol: str) -> str:
    """Trade page for a ticker (``BTR`` → ``.../BTRUSDT``)."""
    raw = symbol.strip().upper()
    pair = raw if raw.endswith("USDT") else f"{raw}USDT"
    return _BYBIT_USDT_TRADE_URL.format(symbol=pair)
