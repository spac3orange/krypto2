# Krypto2 — Telegram → Signal → Bybit USDT Perpetual

Production-oriented pipeline:

```text
Telegram → Telethon → TelegramMessageEvent → dedupe
        → parse → validate → resolve instrument → size
        → TradeIntent → Bybit linear USDT perpetual
        → fill confirm → Take Profit
```

Default `TRADING_MODE=disabled`: parse + structured logs only (safe).

## Requirements

- Python **3.12**
- Telegram user session (MTProto / Telethon)
- Optional: Bybit API key with **Contract Trade** permissions (no withdrawal needed)

## Setup

```bash
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1   # Windows
pip install -e ".[dev]"
cp .env.example .env
```

## Telegram

1. Get `api_id` / `api_hash` from https://my.telegram.org
2. `python -m app.telegram.auth` — creates session under `TELEGRAM_SESSION_PATH`
3. Set exactly one of `TELEGRAM_SOURCE_CHAT_ID` / `TELEGRAM_SOURCE_USERNAME`
4. `python -m app`

## Trading modes

| `TRADING_MODE` | Behavior |
|----------------|----------|
| `disabled` | Parse/log only; no Bybit private calls |
| `demo` | Bybit Demo Trading (`api-demo.bybit.com`). Not testnet |
| `mainnet` | **Only** if `ALLOW_MAINNET_TRADING=true` (kill-switch) |

Unknown mode → startup error. Mainnet never enables by accident.

### TRADE_MARGIN_PCT

Percent of free USDT (`Available` / settle-coin free balance) used as **target initial margin**, not notional and not max loss. Account-wide equity is not used for sizing.

Example:

```text
available = 100 USDT
TRADE_MARGIN_PCT = 1
BYBIT_LEVERAGE = 5

target_margin   = 1 USDT
target_notional ≈ 5 USDT
qty ≈ notional / lastPrice   (rounded DOWN to qtyStep)
```

If rounded qty fails `minOrderQty` / `minNotionalValue`, the signal is **rejected** — qty is never increased to meet exchange minimums.

### Signal → side

- `DUMP` → Buy → open **LONG**
- `PUMP` → Sell → open **SHORT**
- Existing position on symbol → **skip** (`existing_position`)
- Edited messages → skip by default (`EXECUTE_EDITED_MESSAGES=false`)
- Stale messages (`date` older than `MAX_SIGNAL_AGE_SECONDS`) → skip

### Take profit

After fill, TP is set from **actual avg entry** via `POST /v5/position/trading-stop`:

- LONG: `entry * (1 + TAKE_PROFIT_PCT/100)`
- SHORT: `entry * (1 - TAKE_PROFIT_PCT/100)`

Rounded to instrument `tickSize`. Optional SL via `STOP_LOSS_ENABLED` / `STOP_LOSS_PCT`.

### Idempotency

- Durable SQLite journal: `EXECUTION_DB_PATH` (default `data/trading/executions.sqlite3`)
- Deterministic `orderLinkId` = `k2-` + SHA-256(event_id)
- Reserve event_id **before** create; on restart/duplicate → reconcile, never blind re-create
- Uncertain create → lookup by `orderLinkId`, never second submit

## Operator execution

Optional aiogram bot. It does not read the signal chat. It:

- repeats each parsed signal
- reports sent, filled, skipped, and failed orders
- edits runtime trading settings stored in SQLite (`runtime_config` in `EXECUTION_DB_PATH`)

```env
TELEGRAM_BOT_TOKEN=
TELEGRAM_BOT_ADMIN_IDS=123456789
```

Commands: `/start` (short list), `/help` (Russian guide for each setting), `/config`, `/set BYBIT_LEVERAGE 5`, `/set STOP_LOSS_PCT 3`, `/set TRADING_MODE demo`.

When `PROXY_URL` is set, the operator bot uses that proxy for Bot API calls.

API keys, the bot token, and `ALLOW_MAINNET_TRADING` stay in the environment. `TRADING_MODE=mainnet` cannot be set from the bot unless that kill-switch is already true. Changes apply to the next signal without a restart. The Bybit session itself still starts only when `TRADING_MODE` in the environment is `demo` or `mainnet`.

## Bybit API key (Demo Trading)

1. On [bybit.com](https://www.bybit.com), switch to **Demo Trading** and create API keys there
2. Enable unified contract trading permissions
3. Set in `.env`:

```env
TRADING_MODE=demo
BYBIT_API_KEY=...
BYBIT_API_SECRET=...
```

`TRADING_MODE=testnet` is rejected. Demo keys are not mainnet keys and not testnet keys.

Never commit secrets. Never enable withdrawal on trading keys.

## Docker

```bash
docker compose up --build
```

The container runs `python -m app`: Telegram ingestion and, when `TELEGRAM_BOT_TOKEN` and `TELEGRAM_BOT_ADMIN_IDS` are set in `.env`, the operator bot in the same process. Check with `docker compose logs -f` for `bot.started` (or `bot.disabled`). A `PROXY_URL` pointing at `127.0.0.1` refers to the container itself, not the host; use the host address instead.

The container user has UID/GID 1000 by default. Host folders mounted into `/app/data` must be writable by it, otherwise SQLite fails with `unable to open database file`:

```bash
mkdir -p data/telegram data/trading
sudo chown -R 1000:1000 data
```

For another owner, build with `APP_UID=$(id -u) APP_GID=$(id -g) docker compose up -d --build`.

Volumes:

- `./data/telegram` — Telethon session
- `./data/trading` — execution SQLite journal
- `./logs` — JSON logs (`app.jsonl` all events, `errors.jsonl` WARNING+)

Logs rotate daily (14 days kept). Search errors with:

```bash
# Docker host
grep '"level": "ERROR"' logs/errors.jsonl
grep BLUR logs/app.jsonl
```

## Development

```bash
ruff check app tests
mypy app
pytest
```

Opt-in Bybit Demo Trading marker (not default CI):

```bash
# pytest -m bybit_demo  (requires RUN_BYBIT_DEMO=1)
```

## Security

- Telegram session ≡ credential
- Bybit API secret never logged
- Margin mode is **not** auto-switched (UTA account-level)
