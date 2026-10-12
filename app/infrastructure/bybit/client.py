"""pybit HTTP session factory (sync; call via asyncio.to_thread)."""

from __future__ import annotations

from pybit.unified_trading import HTTP

# Bybit rejects signed requests when local time is outside this window (retCode 10002).
# 20s covers a few seconds of clock drift; the exchange maximum is 60s.
_RECV_WINDOW_MS = 20_000


def create_bybit_http(
    *,
    api_key: str,
    api_secret: str,
    demo: bool,
) -> HTTP:
    """Create authenticated Bybit V5 session.

    ``demo=True`` uses Bybit Demo Trading (``api-demo.bybit.com``).
    ``demo=False`` uses mainnet. Testnet is never selected.
    """
    return HTTP(
        testnet=False,
        demo=demo,
        api_key=api_key,
        api_secret=api_secret,
        recv_window=_RECV_WINDOW_MS,
        # One attempt only: a retried POST can create a second order after a timeout.
        max_retries=1,
    )
