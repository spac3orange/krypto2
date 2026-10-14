"""Async Bybit V5 gateway over sync pybit (HTTP + optional private WS)."""

from __future__ import annotations

import asyncio
import logging
import time
from decimal import Decimal
from typing import Any

from pybit.exceptions import InvalidRequestError
from pybit.unified_trading import HTTP, WebSocket

from .enums import OrderSide
from .errors import (
    BybitApiError,
    BybitTransportError,
    ExecutionTimeoutError,
    OrderUncertainError,
)
from .models import (
    AccountSnapshot,
    MarketTicker,
    OrderExecution,
    OrderSubmission,
    PositionSnapshot,
    ResolvedInstrument,
    TakeProfitPlan,
)

logger = logging.getLogger(__name__)


def _d(value: object, default: str = "0") -> Decimal:
    if value is None or value == "":
        return Decimal(default)
    return Decimal(str(value))


class BybitGateway:
    """Async facade over sync pybit HTTP (+ private WS for fill hints)."""

    def __init__(
        self,
        session: HTTP,
        *,
        demo: bool,
        category: str = "linear",
        settle_coin: str = "USDT",
        api_key: str | None = None,
        api_secret: str | None = None,
    ) -> None:
        self._http = session
        self._category = category
        self._settle_coin = settle_coin
        self._demo = demo
        self._api_key = api_key
        self._api_secret = api_secret
        self._ws: WebSocket | None = None
        self._fill_events: dict[str, asyncio.Event] = {}
        self._fill_payloads: dict[str, dict[str, Any]] = {}
        self._loop: asyncio.AbstractEventLoop | None = None

    async def start(self) -> None:
        """Start private WS for order/execution topics (best-effort)."""
        self._loop = asyncio.get_running_loop()
        if not self._api_key or not self._api_secret:
            return

        def _boot() -> WebSocket:
            ws = WebSocket(
                testnet=False,
                demo=self._demo,
                channel_type="private",
                api_key=self._api_key,
                api_secret=self._api_secret,
            )

            def _on_order(message: dict[str, Any]) -> None:
                self._handle_ws_order(message)

            def _on_execution(message: dict[str, Any]) -> None:
                self._handle_ws_execution(message)

            ws.order_stream(callback=_on_order)
            ws.execution_stream(callback=_on_execution)
            return ws

        try:
            self._ws = await asyncio.to_thread(_boot)
            logger.info("Bybit private WebSocket started (demo=%s)", self._demo)
        except Exception:  # noqa: BLE001 — WS is assistive; REST remains source of truth
            logger.warning(
                "Bybit private WebSocket failed to start; REST reconcile only",
                exc_info=True,
            )
            self._ws = None

    async def close(self) -> None:
        self._ws = None

    def _handle_ws_order(self, message: dict[str, Any]) -> None:
        data = message.get("data") or []
        if isinstance(data, dict):
            data = [data]
        for item in data:
            link = item.get("orderLinkId")
            if not link:
                continue
            self._fill_payloads[link] = item
            event = self._fill_events.get(link)
            if event is not None and self._loop is not None:
                self._loop.call_soon_threadsafe(event.set)

    def _handle_ws_execution(self, message: dict[str, Any]) -> None:
        data = message.get("data") or []
        if isinstance(data, dict):
            data = [data]
        for item in data:
            link = item.get("orderLinkId")
            if not link:
                continue
            self._fill_payloads[link] = {**self._fill_payloads.get(link, {}), **item}
            event = self._fill_events.get(link)
            if event is not None and self._loop is not None:
                self._loop.call_soon_threadsafe(event.set)

    async def _call(self, fn: Any, **kwargs: Any) -> dict[str, Any]:
        try:
            result = await asyncio.to_thread(fn, **kwargs)
        except InvalidRequestError as exc:
            raise BybitApiError(exc.status_code, exc.message) from exc
        except Exception as exc:  # network / SDK
            raise BybitTransportError(str(exc)) from exc
        if not isinstance(result, dict):
            raise BybitTransportError("unexpected_bybit_response")
        ret_code = result.get("retCode", result.get("ret_code"))
        if ret_code not in (0, "0", None):
            code: int | str = ret_code if isinstance(ret_code, int | str) else str(ret_code)
            raise BybitApiError(
                code,
                str(result.get("retMsg") or result.get("ret_msg") or ""),
            )
        return result

    async def get_api_key_info(self) -> dict[str, object]:
        """Validate API key; returns safe metadata only (no secrets)."""
        result = await self._call(self._http.get_api_key_information)
        row = result.get("result") or {}
        return {
            "id": row.get("id"),
            "note": row.get("note"),
            "readOnly": row.get("readOnly"),
            "permissions": row.get("permissions"),
        }

    async def get_account_info(self) -> AccountSnapshot:
        result = await self._call(self._http.get_account_info)
        row = result.get("result") or {}
        return AccountSnapshot(
            total_equity=Decimal("0"),
            total_available_balance=Decimal("0"),
            margin_mode=str(row.get("marginMode") or ""),
            unified_margin_status=(
                int(row["unifiedMarginStatus"])
                if row.get("unifiedMarginStatus") is not None
                else None
            ),
        )

    async def get_balance(self) -> AccountSnapshot:
        info = await self.get_account_info()
        result = await self._call(
            self._http.get_wallet_balance,
            accountType="UNIFIED",
        )
        lists = (result.get("result") or {}).get("list") or []
        if not lists:
            return info
        account = lists[0]
        return AccountSnapshot(
            total_equity=_d(account.get("totalEquity")),
            total_available_balance=_d(account.get("totalAvailableBalance")),
            margin_mode=info.margin_mode,
            unified_margin_status=info.unified_margin_status,
        )

    async def get_instrument(self, symbol: str) -> ResolvedInstrument | None:
        result = await self._call(
            self._http.get_instruments_info,
            category=self._category,
            symbol=symbol,
        )
        rows = (result.get("result") or {}).get("list") or []
        if not rows:
            return None
        row = rows[0]
        lot = row.get("lotSizeFilter") or {}
        lev = row.get("leverageFilter") or {}
        price = row.get("priceFilter") or {}
        return ResolvedInstrument(
            symbol=str(row.get("symbol")),
            status=str(row.get("status") or ""),
            contract_type=str(row.get("contractType") or ""),
            base_coin=str(row.get("baseCoin") or ""),
            quote_coin=str(row.get("quoteCoin") or ""),
            settle_coin=str(row.get("settleCoin") or ""),
            min_leverage=_d(lev.get("minLeverage"), "1"),
            max_leverage=_d(lev.get("maxLeverage"), "1"),
            leverage_step=_d(lev.get("leverageStep"), "1"),
            min_notional_value=_d(lot.get("minNotionalValue"), "0"),
            min_order_qty=_d(lot.get("minOrderQty"), "0"),
            qty_step=_d(lot.get("qtyStep"), "0.001"),
            max_mkt_order_qty=_d(lot.get("maxMktOrderQty"), lot.get("maxOrderQty") or "0"),
            tick_size=_d(price.get("tickSize"), "0.01"),
        )

    async def get_ticker(self, symbol: str) -> MarketTicker:
        result = await self._call(
            self._http.get_tickers,
            category=self._category,
            symbol=symbol,
        )
        rows = (result.get("result") or {}).get("list") or []
        if not rows:
            raise BybitApiError(-1, "ticker_not_found")
        row = rows[0]
        return MarketTicker(
            symbol=symbol,
            last_price=_d(row.get("lastPrice")),
            mark_price=_d(row.get("markPrice")),
        )

    async def get_position(self, symbol: str) -> PositionSnapshot:
        result = await self._call(
            self._http.get_positions,
            category=self._category,
            symbol=symbol,
            settleCoin=self._settle_coin,
        )
        rows = (result.get("result") or {}).get("list") or []
        if not rows:
            return PositionSnapshot(
                symbol=symbol,
                size=Decimal("0"),
                side=None,
                avg_price=None,
                leverage=None,
            )
        row = rows[0]
        return PositionSnapshot(
            symbol=symbol,
            size=_d(row.get("size")),
            side=str(row.get("side") or "") or None,
            avg_price=_d(row.get("avgPrice")) if row.get("avgPrice") not in (None, "") else None,
            leverage=_d(row.get("leverage")) if row.get("leverage") not in (None, "") else None,
        )

    async def set_leverage(self, symbol: str, leverage: Decimal) -> None:
        lev = str(leverage)
        try:
            await self._call(
                self._http.set_leverage,
                category=self._category,
                symbol=symbol,
                buyLeverage=lev,
                sellLeverage=lev,
            )
        except BybitApiError as exc:
            # 110043: leverage not modified
            if str(exc.ret_code) in {"110043"}:
                return
            raise

    async def place_order(
        self,
        *,
        symbol: str,
        side: OrderSide,
        qty: Decimal,
        order_link_id: str,
        take_profit: Decimal | None = None,
        stop_loss: Decimal | None = None,
        tp_trigger_by: str | None = None,
        sl_trigger_by: str | None = None,
    ) -> OrderSubmission:
        payload: dict[str, Any] = {
            "category": self._category,
            "symbol": symbol,
            "side": side.value,
            "orderType": "Market",
            "qty": str(qty),
            "positionIdx": 0,
            "reduceOnly": False,
            "orderLinkId": order_link_id,
        }
        if take_profit is not None:
            payload["takeProfit"] = str(take_profit)
            if tp_trigger_by:
                payload["tpTriggerBy"] = tp_trigger_by
        if stop_loss is not None:
            payload["stopLoss"] = str(stop_loss)
            if sl_trigger_by:
                payload["slTriggerBy"] = sl_trigger_by

        try:
            result = await self._call(self._http.place_order, **payload)
        except BybitTransportError as exc:
            raise OrderUncertainError("place_order transport failure") from exc
        except BybitApiError as exc:
            # Duplicate orderLinkId → reconcile, do not place again.
            if str(exc.ret_code) in {"110072", "20001", "10001"} and "link" in exc.ret_msg.lower():
                raise OrderUncertainError("duplicate_or_uncertain_order_link") from exc
            raise

        row = result.get("result") or {}
        return OrderSubmission(
            order_id=str(row.get("orderId") or ""),
            order_link_id=str(row.get("orderLinkId") or order_link_id),
            symbol=symbol,
            side=side,
            qty=qty,
            status=str(row.get("orderStatus") or "Created"),
        )

    async def get_order_by_link_id(self, symbol: str, order_link_id: str) -> OrderExecution | None:
        queries: list[dict[str, Any]] = [
            {
                "fn": self._http.get_open_orders,
                "kwargs": {
                    "category": self._category,
                    "symbol": symbol,
                    "orderLinkId": order_link_id,
                },
            },
            {
                "fn": self._http.get_order_history,
                "kwargs": {
                    "category": self._category,
                    "symbol": symbol,
                    "orderLinkId": order_link_id,
                },
            },
        ]
        for query in queries:
            try:
                result = await self._call(query["fn"], **query["kwargs"])
            except (BybitApiError, BybitTransportError):
                continue
            rows = (result.get("result") or {}).get("list") or []
            if not rows:
                continue
            return self._row_to_execution(rows[0], symbol=symbol, order_link_id=order_link_id)
        return None

    async def set_trading_stop(self, *, symbol: str, plan: TakeProfitPlan) -> None:
        payload: dict[str, Any] = {
            "category": self._category,
            "symbol": symbol,
            "tpslMode": "Full",
            "positionIdx": 0,
        }
        if plan.take_profit_price is not None:
            payload["takeProfit"] = str(plan.take_profit_price)
            payload["tpTriggerBy"] = plan.tp_trigger_by
        if plan.stop_loss_price is not None:
            payload["stopLoss"] = str(plan.stop_loss_price)
            if plan.sl_trigger_by:
                payload["slTriggerBy"] = plan.sl_trigger_by
        try:
            await self._call(self._http.set_trading_stop, **payload)
        except BybitApiError as exc:
            # 34040: TP/SL already match values attached on create.
            if str(exc.ret_code) != "34040":
                raise
            logger.info("Take profit / stop loss already set for %s", symbol)

    async def wait_for_fill(
        self,
        *,
        symbol: str,
        order_link_id: str,
        timeout_sec: float,
    ) -> OrderExecution:
        event = asyncio.Event()
        self._fill_events[order_link_id] = event
        deadline = time.monotonic() + timeout_sec
        try:
            while time.monotonic() < deadline:
                found = await self.get_order_by_link_id(symbol, order_link_id)
                if found is not None and self._is_terminal_or_filled(found):
                    return found
                try:
                    await asyncio.wait_for(event.wait(), timeout=0.5)
                    event.clear()
                except TimeoutError:
                    continue
            found = await self.get_order_by_link_id(symbol, order_link_id)
            if found is not None:
                return found
            raise ExecutionTimeoutError(f"fill timeout for {order_link_id}")
        finally:
            self._fill_events.pop(order_link_id, None)

    @staticmethod
    def _is_terminal_or_filled(order: OrderExecution) -> bool:
        status = order.status.lower()
        if status in {"filled", "cancelled", "rejected", "deactivated"}:
            return True
        return order.filled_qty > 0 and order.avg_price is not None

    @staticmethod
    def _row_to_execution(
        row: dict[str, Any],
        *,
        symbol: str,
        order_link_id: str,
    ) -> OrderExecution:
        side_raw = str(row.get("side") or "Buy")
        side = OrderSide.BUY if side_raw.lower() == "buy" else OrderSide.SELL
        avg = row.get("avgPrice")
        return OrderExecution(
            order_id=str(row.get("orderId") or ""),
            order_link_id=str(row.get("orderLinkId") or order_link_id),
            symbol=symbol,
            side=side,
            qty=_d(row.get("qty")),
            filled_qty=_d(row.get("cumExecQty") or "0"),
            avg_price=_d(avg) if avg not in (None, "", "0", "0.00") else None,
            status=str(row.get("orderStatus") or ""),
            cum_exec_qty=_d(row.get("cumExecQty")) if row.get("cumExecQty") is not None else None,
        )
