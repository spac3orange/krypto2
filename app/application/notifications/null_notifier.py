"""Notifier that drops every message."""

from __future__ import annotations

from app.domain.notifications.models import OrderNotice, SignalNotice


class NullOperatorNotifier:
    """Used when the operator bot is not configured."""

    async def signal_detected(self, notice: SignalNotice) -> None:
        return

    async def order_update(self, notice: OrderNotice) -> None:
        return
