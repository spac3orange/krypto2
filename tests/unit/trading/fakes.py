"""In-memory fake TradingGateway for deterministic unit tests."""

from __future__ import annotations

from decimal import Decimal

from app.core.errors import OrderUncertainError
from app.domain.trading.enums import OrderSide
from app.domain.trading.models import (
    AccountSnapshot,
    MarketTicker,
    OpenOrderSnapshot,
    OrderExecution,
    OrderSubmission,
    PositionSnapshot,
    ResolvedInstrument,
    TakeProfitPlan,
)


class FakeTradingGateway:
    """Controllable gateway used by orchestrator / sizer tests."""

    def __init__(self) -> None:
        self.account = AccountSnapshot(
            total_equity=Decimal("100"),
            total_available_balance=Decimal("100"),
            margin_mode="REGULAR_MARGIN",
            unified_margin_status=5,
        )
        self.instruments: dict[str, ResolvedInstrument] = {}
        self.tickers: dict[str, MarketTicker] = {}
        self.positions: dict[str, PositionSnapshot] = {}
        self.orders_by_link: dict[str, OrderExecution] = {}
        self.open_orders: list[OpenOrderSnapshot] = []
        self.placed: list[dict[str, object]] = []
        self.leverage_calls: list[tuple[str, Decimal]] = []
        self.trading_stops: list[tuple[str, TakeProfitPlan]] = []
        self.place_raises_uncertain = False
        self.fail_place = False

    def add_linear_usdt(
        self,
        symbol: str,
        *,
        tick_size: str = "0.0001",
        qty_step: str = "1",
        min_qty: str = "1",
        min_notional: str = "5",
        max_mkt: str = "1000000",
        max_lev: str = "50",
        last_price: str = "0.50",
        status: str = "Trading",
    ) -> None:
        self.instruments[symbol] = ResolvedInstrument(
            symbol=symbol,
            status=status,
            contract_type="LinearPerpetual",
            base_coin=symbol.replace("USDT", ""),
            quote_coin="USDT",
            settle_coin="USDT",
            min_leverage=Decimal("1"),
            max_leverage=Decimal(max_lev),
            leverage_step=Decimal("0.01"),
            min_notional_value=Decimal(min_notional),
            min_order_qty=Decimal(min_qty),
            qty_step=Decimal(qty_step),
            max_mkt_order_qty=Decimal(max_mkt),
            tick_size=Decimal(tick_size),
        )
        self.tickers[symbol] = MarketTicker(
            symbol=symbol,
            last_price=Decimal(last_price),
            mark_price=Decimal(last_price),
        )
        self.positions[symbol] = PositionSnapshot(
            symbol=symbol,
            size=Decimal("0"),
            side=None,
            avg_price=None,
            leverage=None,
        )

    async def get_api_key_info(self) -> dict[str, object]:
        return {"id": "fake", "readOnly": 0, "permissions": {}}

    async def get_account_info(self) -> AccountSnapshot:
        return self.account

    async def get_balance(self) -> AccountSnapshot:
        return self.account

    async def get_instrument(self, symbol: str) -> ResolvedInstrument | None:
        return self.instruments.get(symbol)

    async def get_ticker(self, symbol: str) -> MarketTicker:
        return self.tickers[symbol]

    async def get_position(self, symbol: str) -> PositionSnapshot:
        empty = PositionSnapshot(
            symbol=symbol,
            size=Decimal("0"),
            side=None,
            avg_price=None,
            leverage=None,
        )
        return self.positions.get(symbol, empty)

    async def list_open_positions(self) -> list[PositionSnapshot]:
        return [pos for pos in self.positions.values() if pos.size != 0]

    async def list_open_orders(self) -> list[OpenOrderSnapshot]:
        return list(self.open_orders)

    async def set_leverage(self, symbol: str, leverage: Decimal) -> None:
        self.leverage_calls.append((symbol, leverage))

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
        self.placed.append(
            {
                "symbol": symbol,
                "side": side,
                "qty": qty,
                "order_link_id": order_link_id,
                "take_profit": take_profit,
                "stop_loss": stop_loss,
            }
        )
        if self.place_raises_uncertain:
            # Simulate: exchange accepted but client timed out; order exists.
            self.orders_by_link[order_link_id] = OrderExecution(
                order_id="ord-unc",
                order_link_id=order_link_id,
                symbol=symbol,
                side=side,
                qty=qty,
                filled_qty=qty,
                avg_price=self.tickers[symbol].last_price,
                status="Filled",
            )
            raise OrderUncertainError("simulated uncertain")
        if self.fail_place:
            raise OrderUncertainError("failed without remote order")

        order = OrderExecution(
            order_id=f"ord-{len(self.placed)}",
            order_link_id=order_link_id,
            symbol=symbol,
            side=side,
            qty=qty,
            filled_qty=qty,
            avg_price=self.tickers[symbol].last_price,
            status="Filled",
        )
        self.orders_by_link[order_link_id] = order
        return OrderSubmission(
            order_id=order.order_id,
            order_link_id=order_link_id,
            symbol=symbol,
            side=side,
            qty=qty,
            status="Created",
        )

    async def get_order_by_link_id(self, symbol: str, order_link_id: str) -> OrderExecution | None:
        return self.orders_by_link.get(order_link_id)

    async def set_trading_stop(self, *, symbol: str, plan: TakeProfitPlan) -> None:
        self.trading_stops.append((symbol, plan))

    async def wait_for_fill(
        self,
        *,
        symbol: str,
        order_link_id: str,
        timeout_sec: float,
    ) -> OrderExecution:
        order = self.orders_by_link.get(order_link_id)
        assert order is not None
        return order
