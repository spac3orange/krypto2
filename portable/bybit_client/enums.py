"""Minimal enums used by the Bybit gateway."""

from __future__ import annotations

from enum import StrEnum


class OrderSide(StrEnum):
    """Bybit order side for linear perpetuals."""

    BUY = "Buy"
    SELL = "Sell"
