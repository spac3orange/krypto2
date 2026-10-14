# bybit_client — portable Bybit V5 module

Self-contained async wrapper around **pybit** for Bybit **Demo Trading** and **mainnet** USDT linear perpetuals. Extracted from krypto2 so you can copy the folder into another Python 3.12+ project.

## Copy into another program

1. Copy the whole folder `bybit_client/` next to your app (or into a package path).
2. Install dependency: `pip install -r bybit_client/requirements.txt` (= `pybit==5.17.0`).
3. Import:

```python
from bybit_client import BybitGateway, OrderSide, create_bybit_http, usdt_perp_trade_url
```

No imports from krypto2 / Telegram / SQLite.

## What is included

| File | Role |
|------|------|
| `client.py` | HTTP session factory (`demo=True` → api-demo.bybit.com) |
| `gateway.py` | Async API: balance, instrument, ticker, position, leverage, market order, TP/SL, wait fill |
| `models.py` | Frozen dataclasses |
| `enums.py` | `OrderSide` |
| `errors.py` | `BybitApiError`, `BybitTransportError`, `OrderUncertainError`, … |
| `urls.py` | Public trade-page URL helper |
| `example.py` | Read-only smoke test |

## Quick start

```python
import asyncio
from decimal import Decimal
from bybit_client import BybitGateway, OrderSide, create_bybit_http

async def run() -> None:
    http = create_bybit_http(api_key="...", api_secret="...", demo=True)
    gw = BybitGateway(http, demo=True, api_key="...", api_secret="...")
    await gw.start()
    try:
        bal = await gw.get_balance()
        print(bal.total_equity)
        # Market order example (unique order_link_id required for idempotency):
        # sub = await gw.place_order(
        #     symbol="BTCUSDT",
        #     side=OrderSide.BUY,
        #     qty=Decimal("0.001"),
        #     order_link_id="myapp-unique-id-1",
        # )
        # fill = await gw.wait_for_fill(symbol="BTCUSDT", order_link_id=sub.order_link_id, timeout_sec=30)
    finally:
        await gw.close()

asyncio.run(run())
```

Demo keys must be created inside Bybit **Demo Trading**. They are not mainnet and not testnet keys.

## Safety notes (keep when integrating)

- `max_retries=1` — do not raise this for POSTs; a timeout + retry can double-fill.
- On `OrderUncertainError`, call `get_order_by_link_id` — never place a second order with a new link id for the same intent.
- `set_trading_stop` treats Bybit `34040` (already set) as success.
- Leverage `110043` (unchanged) is ignored.
- Never log `api_key` / `api_secret`.
- Testnet (`api-testnet.bybit.com`) is intentionally unsupported.

## Not included (lives in the host app)

Signal parsing, risk, Telegram, SQLite journal, operator bot, position sizing — those stay in krypto2. This package is only the exchange adapter.
