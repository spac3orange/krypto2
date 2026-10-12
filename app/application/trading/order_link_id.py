"""Deterministic Bybit orderLinkId generation."""

from __future__ import annotations

import hashlib


def build_order_link_id(event_id: str, *, max_len: int = 36) -> str:
    """Build a deterministic, exchange-safe orderLinkId from ``event_id``.

    Bybit orderLinkId has length limits; we use a short prefixed hash rather than
    embedding the full Telegram event_id.
    """
    digest = hashlib.sha256(event_id.encode("utf-8")).hexdigest()
    prefix = "k2-"
    body_len = max_len - len(prefix)
    if body_len < 8:
        msg = "max_len too small for orderLinkId"
        raise ValueError(msg)
    return prefix + digest[:body_len]
