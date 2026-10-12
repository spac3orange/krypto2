"""Notices sent to the operator bot (transport-free)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class OrderUpdateKind(StrEnum):
    """What happened to an order attempt."""

    SUBMITTED = "submitted"
    FILLED = "filled"
    SKIPPED = "skipped"
    REJECTED = "rejected"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class SignalNotice:
    """A parsed signal worth showing to the operator."""

    symbol: str
    signal_type: str
    action: str
    timeframe: str
    change_percent: str
    price_from: str
    price_to: str


@dataclass(frozen=True, slots=True)
class OrderNotice:
    """Outcome of trying to place or finish an order."""

    symbol: str
    kind: OrderUpdateKind
    side: str | None = None
    reason: str | None = None
    qty: str | None = None
    avg_price: str | None = None
    take_profit: str | None = None
    stop_loss: str | None = None
