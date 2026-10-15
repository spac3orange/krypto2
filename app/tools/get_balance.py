"""Print Bybit UNIFIED balance via API (no Telegram).

Usage::

    python -m app.tools.get_balance
"""

from __future__ import annotations

import asyncio
import sys

from app.core.config import load_settings
from app.core.errors import ConfigurationError
from app.core.logging import setup_logging
from app.domain.trading.enums import TradingMode
from app.infrastructure.bybit.client import create_bybit_http
from app.infrastructure.bybit.gateway import BybitGateway


async def _run() -> None:
    settings = load_settings()
    setup_logging(settings.log_level, log_dir=settings.log_dir)
    if settings.trading_mode is TradingMode.DISABLED:
        print("TRADING_MODE=disabled — баланс через API недоступен", file=sys.stderr)
        raise SystemExit(2)
    if settings.bybit_api_key is None or settings.bybit_api_secret is None:
        print("BYBIT_API_KEY / BYBIT_API_SECRET не заданы", file=sys.stderr)
        raise SystemExit(2)

    http = create_bybit_http(
        api_key=settings.bybit_api_key,
        api_secret=settings.bybit_api_secret,
        demo=settings.bybit_demo,
    )
    gateway = BybitGateway(
        http,
        demo=settings.bybit_demo,
        category=settings.bybit_category,
        settle_coin=settings.bybit_settle_coin,
        api_key=settings.bybit_api_key,
        api_secret=settings.bybit_api_secret,
    )
    await gateway.start()
    try:
        balance = await gateway.get_balance()
        print(f"mode={settings.trading_mode.value}")
        print(f"equity={balance.total_equity}")
        print(f"available={balance.total_available_balance}")
        print(f"margin_mode={balance.margin_mode}")
        print(f"unified_margin_status={balance.unified_margin_status}")
        print(f"account_type={balance.account_type}")
    finally:
        await gateway.close()


def main() -> None:
    try:
        asyncio.run(_run())
    except ConfigurationError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc


if __name__ == "__main__":
    main()
