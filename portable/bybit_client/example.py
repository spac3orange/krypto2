"""Minimal smoke example. Does not place orders.

Usage (from the parent of ``bybit_client``)::

    set BYBIT_API_KEY=...
    set BYBIT_API_SECRET=...
    python -m bybit_client.example
"""

from __future__ import annotations

import asyncio
import os
import sys

from .client import create_bybit_http
from .gateway import BybitGateway
from .urls import usdt_perp_trade_url


async def main() -> None:
    api_key = os.environ.get("BYBIT_API_KEY", "").strip()
    api_secret = os.environ.get("BYBIT_API_SECRET", "").strip()
    if not api_key or not api_secret:
        print("Set BYBIT_API_KEY and BYBIT_API_SECRET", file=sys.stderr)
        raise SystemExit(2)

    demo = os.environ.get("BYBIT_DEMO", "true").strip().lower() not in {"0", "false", "no"}
    http = create_bybit_http(api_key=api_key, api_secret=api_secret, demo=demo)
    gateway = BybitGateway(
        http,
        demo=demo,
        api_key=api_key,
        api_secret=api_secret,
    )
    await gateway.start()
    try:
        key_info = await gateway.get_api_key_info()
        balance = await gateway.get_balance()
        ticker = await gateway.get_ticker("BTCUSDT")
        print("demo=", demo)
        print("key_id=", key_info.get("id"), "readOnly=", key_info.get("readOnly"))
        print("equity=", balance.total_equity, "margin_mode=", balance.margin_mode)
        print("BTC last=", ticker.last_price, "mark=", ticker.mark_price)
        print("trade_url=", usdt_perp_trade_url("BTC"))
    finally:
        await gateway.close()


if __name__ == "__main__":
    asyncio.run(main())
