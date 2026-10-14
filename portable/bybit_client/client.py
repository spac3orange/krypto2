"""pybit HTTP session factory (sync; call gateway methods via asyncio)."""

from __future__ import annotations

from pybit.unified_trading import HTTP

# Bybit rejects signed requests when local time is outside this window (retCode 10002).
_RECV_WINDOW_MS = 20_000


def create_bybit_http(
    *,
    api_key: str,
    api_secret: str,
    demo: bool,
) -> HTTP:
    """Create authenticated Bybit V5 session.

    ``demo=True`` → Demo Trading (``api-demo.bybit.com``).
    ``demo=False`` → mainnet. Testnet is never selected.
    ``max_retries=1`` so a timed-out POST is not blindly retried into a second order.
    """
    return HTTP(
        testnet=False,
        demo=demo,
        api_key=api_key,
        api_secret=api_secret,
        recv_window=_RECV_WINDOW_MS,
        max_retries=1,
    )
