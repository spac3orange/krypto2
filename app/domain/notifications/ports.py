"""Outbound port for operator notifications."""

from __future__ import annotations

from typing import Protocol

from app.domain.notifications.models import OrderNotice, SignalNotice


class OperatorNotifier(Protocol):
    """Delivers signal and order updates. Must not raise into the trading path."""

    async def signal_detected(self, notice: SignalNotice) -> None:
        """Report a parsed signal."""

    async def order_update(self, notice: OrderNotice) -> None:
        """Report an order submission or its outcome."""
