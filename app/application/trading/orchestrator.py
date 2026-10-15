"""End-to-end trading signal orchestrator (no pybit imports)."""

from __future__ import annotations

import asyncio
import logging
import uuid
from decimal import Decimal

from app.application.notifications.null_notifier import NullOperatorNotifier
from app.application.trading.decimal_math import calc_stop_loss_price, calc_take_profit_price
from app.application.trading.instrument_resolver import BybitInstrumentResolver
from app.application.trading.order_link_id import build_order_link_id
from app.application.trading.position_sizer import PositionSizer
from app.application.trading.runtime_config_service import SettingsRuntimeConfig
from app.application.trading.validator import SignalValidator
from app.core.config import Settings
from app.core.errors import (
    AppError,
    BelowMinNotionalError,
    ExistingPositionError,
    InstrumentConstraintError,
    InstrumentNotFoundError,
    InsufficientBalanceError,
    OrderUncertainError,
    SignalValidationError,
)
from app.core.logging import log_event
from app.domain.notifications.models import OrderNotice, OrderUpdateKind
from app.domain.notifications.ports import OperatorNotifier
from app.domain.telegram.models import TelegramMessageEvent
from app.domain.trading.enums import (
    ExecutionStatus,
    OrderSide,
    OrderSizingPrice,
    PositionDirection,
    TradeAction,
    TradingMode,
    TradingSignalType,
)
from app.domain.trading.models import (
    ParsedTradingSignal,
    TakeProfitPlan,
    TradeIntent,
)
from app.domain.trading.ports import ExecutionStore, TradingGateway
from app.domain.trading.runtime_config import RuntimeConfigSource, RuntimeTradingConfig

logger = logging.getLogger(__name__)


class TradingSignalOrchestrator:
    """Validate → resolve → size → idempotent execute → TP."""

    def __init__(
        self,
        settings: Settings,
        *,
        gateway: TradingGateway,
        store: ExecutionStore,
        validator: SignalValidator | None = None,
        resolver: BybitInstrumentResolver | None = None,
        sizer: PositionSizer | None = None,
        config_source: RuntimeConfigSource | None = None,
        notifier: OperatorNotifier | None = None,
    ) -> None:
        self._settings = settings
        self._gateway = gateway
        self._store = store
        self._config = config_source or SettingsRuntimeConfig(settings)
        self._notifier = notifier or NullOperatorNotifier()
        self._validator = validator or SignalValidator(self._config)
        self._resolver = resolver or BybitInstrumentResolver(
            gateway,
            settle_coin=settings.bybit_settle_coin,
        )
        self._sizer = sizer or PositionSizer()

    async def handle(
        self,
        event: TelegramMessageEvent,
        signal: ParsedTradingSignal,
    ) -> None:
        correlation_id = str(uuid.uuid4())
        base_fields = {
            "correlation_id": correlation_id,
            "event_id": event.event_id,
            "chat_id": event.chat_id,
            "message_id": event.message_id,
            "telegram_event_type": event.event_type.value,
            "symbol_raw": signal.symbol,
            "signal_type": signal.signal_type.value,
            "action": signal.action.value,
        }
        runtime = self._config.get()
        if runtime.trading_mode is TradingMode.DISABLED:
            await self._announce(
                OrderNotice(
                    symbol=signal.symbol,
                    kind=OrderUpdateKind.SKIPPED,
                    side=signal.action.value,
                    reason="trading_disabled",
                )
            )
            log_event(
                logger,
                logging.INFO,
                "trading.signal.skipped",
                "Trading signal skipped because runtime mode is disabled",
                reason="trading_disabled",
                **base_fields,
            )
            return
        if not runtime.orders_enabled:
            await self._announce(
                OrderNotice(
                    symbol=signal.symbol,
                    kind=OrderUpdateKind.SKIPPED,
                    side=signal.action.value,
                    reason="orders_disabled",
                )
            )
            log_event(
                logger,
                logging.INFO,
                "trading.signal.skipped",
                "Trading signal skipped because order placement is disabled",
                reason="orders_disabled",
                **base_fields,
            )
            return
        if not self._reacts_to(signal.signal_type, runtime):
            reason = f"signal_disabled_{signal.signal_type.value.lower()}"
            await self._announce(
                OrderNotice(
                    symbol=signal.symbol,
                    kind=OrderUpdateKind.SKIPPED,
                    side=signal.action.value,
                    reason=reason,
                )
            )
            log_event(
                logger,
                logging.INFO,
                "trading.signal.skipped",
                "Trading signal skipped by reaction toggle",
                reason=reason,
                **base_fields,
            )
            return
        if runtime.trading_mode is TradingMode.MAINNET and not self._settings.allow_mainnet_trading:
            await self._announce(
                OrderNotice(
                    symbol=signal.symbol,
                    kind=OrderUpdateKind.REJECTED,
                    side=signal.action.value,
                    reason="mainnet_not_allowed",
                )
            )
            return

        try:
            outcome = self._validator.validate(event, signal)
            if not outcome.ok:
                await self._announce(
                    OrderNotice(
                        symbol=signal.symbol,
                        kind=OrderUpdateKind.SKIPPED,
                        side=signal.action.value,
                        reason=outcome.reason,
                    )
                )
                log_event(
                    logger,
                    logging.INFO,
                    "trading.signal.skipped",
                    "Trading signal skipped by validator",
                    reason=outcome.reason,
                    **base_fields,
                )
                return

            log_event(
                logger,
                logging.INFO,
                "trading.signal.validated",
                "Trading signal validated",
                **base_fields,
            )

            existing = self._store.get_by_event_id(event.event_id)
            if existing is not None:
                await self._reconcile_existing(event, existing.order_link_id, base_fields)
                return

            instrument = await self._resolver.resolve(signal.symbol)
            log_event(
                logger,
                logging.INFO,
                "trading.instrument.resolved",
                "Instrument resolved",
                symbol=instrument.symbol,
                **base_fields,
            )

            if runtime.bybit_leverage > instrument.max_leverage:
                await self._announce(
                    OrderNotice(
                        symbol=instrument.symbol,
                        kind=OrderUpdateKind.REJECTED,
                        side=signal.action.value,
                        reason="leverage_above_max",
                    )
                )
                log_event(
                    logger,
                    logging.WARNING,
                    "trading.signal.rejected",
                    "Configured leverage above instrument max",
                    reason="leverage_above_max",
                    symbol=instrument.symbol,
                    **base_fields,
                )
                return

            position = await self._gateway.get_position(instrument.symbol)
            if position.size > 0:
                await self._announce(
                    OrderNotice(
                        symbol=instrument.symbol,
                        kind=OrderUpdateKind.SKIPPED,
                        side=signal.action.value,
                        reason="existing_position",
                    )
                )
                log_event(
                    logger,
                    logging.INFO,
                    "trading.signal.skipped",
                    "Skipped due to existing open position",
                    reason="existing_position",
                    symbol=instrument.symbol,
                    position_size=str(position.size),
                    **base_fields,
                )
                return

            account = await self._gateway.get_balance()
            ticker = await self._gateway.get_ticker(instrument.symbol)
            price = (
                ticker.last_price
                if runtime.order_sizing_price is OrderSizingPrice.LAST_PRICE
                else ticker.mark_price
            )

            sized = self._sizer.size(
                account=account,
                instrument=instrument,
                ticker=ticker,
                trade_margin_pct=runtime.trade_margin_pct,
                leverage=runtime.bybit_leverage,
                sizing_price=price,
            )
            log_event(
                logger,
                logging.INFO,
                "trading.position.sized",
                "Position sized from available USDT allocation",
                symbol=instrument.symbol,
                target_margin=str(sized.target_margin),
                target_notional=str(sized.target_notional),
                quantity=str(sized.quantity),
                sizing_price=str(sized.sizing_price),
                leverage=str(runtime.bybit_leverage),
                **base_fields,
            )

            side, direction = self._map_side(signal.action)
            order_link_id = build_order_link_id(event.event_id)

            provisional_tp: Decimal | None = None
            provisional_sl: Decimal | None = None
            if runtime.take_profit_enabled:
                provisional_tp = calc_take_profit_price(
                    avg_entry=price,
                    take_profit_pct=runtime.take_profit_pct,
                    direction=direction,
                    tick_size=instrument.tick_size,
                )
            if runtime.stop_loss_enabled and runtime.stop_loss_pct is not None:
                provisional_sl = calc_stop_loss_price(
                    avg_entry=price,
                    stop_loss_pct=runtime.stop_loss_pct,
                    direction=direction,
                    tick_size=instrument.tick_size,
                )

            intent = TradeIntent(
                correlation_id=correlation_id,
                source_event_id=event.event_id,
                order_link_id=order_link_id,
                symbol=instrument.symbol,
                category=self._settings.bybit_category,
                side=side,
                direction=direction,
                leverage=runtime.bybit_leverage,
                target_margin=sized.target_margin,
                target_notional=sized.target_notional,
                quantity=sized.quantity,
                sizing_price=sized.sizing_price,
                signal_type=signal.signal_type,
                action=signal.action,
                timeframe=signal.timeframe,
                take_profit_pct=(
                    runtime.take_profit_pct if runtime.take_profit_enabled else None
                ),
                stop_loss_pct=(runtime.stop_loss_pct if runtime.stop_loss_enabled else None),
                tp_trigger_by=self._settings.take_profit_trigger_by,
                provisional_take_profit=provisional_tp,
                provisional_stop_loss=provisional_sl,
            )

            if runtime.order_open_delay_sec > 0:
                log_event(
                    logger,
                    logging.INFO,
                    "trading.order.delay",
                    "Waiting before order submit",
                    delay_sec=runtime.order_open_delay_sec,
                    **base_fields,
                )
                await asyncio.sleep(runtime.order_open_delay_sec)

            await self._execute(intent, instrument.tick_size, base_fields)

        except SignalValidationError as exc:
            await self._announce(
                OrderNotice(
                    symbol=signal.symbol,
                    kind=OrderUpdateKind.SKIPPED,
                    side=signal.action.value,
                    reason=exc.reason,
                )
            )
            log_event(
                logger,
                logging.INFO,
                "trading.signal.skipped",
                "Trading signal skipped",
                reason=exc.reason,
                **base_fields,
            )
        except InstrumentNotFoundError as exc:
            await self._announce(
                OrderNotice(
                    symbol=signal.symbol,
                    kind=OrderUpdateKind.REJECTED,
                    side=signal.action.value,
                    reason="instrument_not_found",
                )
            )
            log_event(
                logger,
                logging.WARNING,
                "trading.signal.rejected",
                "Instrument not found",
                reason="instrument_not_found",
                symbol=exc.symbol,
                **base_fields,
            )
        except (BelowMinNotionalError, InstrumentConstraintError) as exc:
            reason = getattr(exc, "reason", "instrument_constraint")
            await self._announce(
                OrderNotice(
                    symbol=signal.symbol,
                    kind=OrderUpdateKind.REJECTED,
                    side=signal.action.value,
                    reason=str(reason),
                )
            )
            log_event(
                logger,
                logging.WARNING,
                "trading.signal.rejected",
                "Trade rejected by instrument constraints",
                reason=reason,
                **base_fields,
            )
        except InsufficientBalanceError:
            await self._announce(
                OrderNotice(
                    symbol=signal.symbol,
                    kind=OrderUpdateKind.REJECTED,
                    side=signal.action.value,
                    reason="insufficient_available_balance",
                )
            )
            log_event(
                logger,
                logging.WARNING,
                "trading.trade.rejected",
                "Insufficient available balance",
                reason="insufficient_available_balance",
                **base_fields,
            )
        except ExistingPositionError:
            await self._announce(
                OrderNotice(
                    symbol=signal.symbol,
                    kind=OrderUpdateKind.SKIPPED,
                    side=signal.action.value,
                    reason="existing_position",
                )
            )
            log_event(
                logger,
                logging.INFO,
                "trading.signal.skipped",
                "Existing position",
                reason="existing_position",
                **base_fields,
            )
        except OrderUncertainError as exc:
            await self._announce(
                OrderNotice(
                    symbol=signal.symbol,
                    kind=OrderUpdateKind.FAILED,
                    side=signal.action.value,
                    reason="order_uncertain",
                )
            )
            log_event(
                logger,
                logging.ERROR,
                "trading.execution.failed",
                "Order result uncertain; reconcile without re-submit",
                reason="order_uncertain",
                error=str(exc),
                **base_fields,
            )
        except AppError as exc:
            await self._announce(
                OrderNotice(
                    symbol=signal.symbol,
                    kind=OrderUpdateKind.FAILED,
                    side=signal.action.value,
                    reason=type(exc).__name__,
                )
            )
            log_event(
                logger,
                logging.ERROR,
                "trading.execution.failed",
                "Trading execution failed",
                reason=type(exc).__name__,
                error=str(exc),
                **base_fields,
            )
        except Exception as exc:  # noqa: BLE001 — isolate per-signal failures
            await self._announce(
                OrderNotice(
                    symbol=signal.symbol,
                    kind=OrderUpdateKind.FAILED,
                    side=signal.action.value,
                    reason=type(exc).__name__,
                )
            )
            log_event(
                logger,
                logging.ERROR,
                "trading.execution.failed",
                "Unexpected trading failure",
                reason="unexpected_error",
                error_type=type(exc).__name__,
                error=str(exc),
                **base_fields,
            )

    async def _execute(
        self,
        intent: TradeIntent,
        tick_size: Decimal,
        base_fields: dict[str, object],
    ) -> None:
        fields = {
            **base_fields,
            "order_link_id": intent.order_link_id,
            "symbol": intent.symbol,
            "side": intent.side.value,
        }

        # Crash-safe: reserve BEFORE create. Duplicate → reconcile path.
        existing = self._store.get_by_event_id(intent.source_event_id)
        if existing is not None:
            await self._reconcile_existing(None, intent.order_link_id, fields, symbol=intent.symbol)
            return

        try:
            self._store.reserve(
                event_id=intent.source_event_id,
                order_link_id=intent.order_link_id,
                correlation_id=intent.correlation_id,
                symbol=intent.symbol,
                side=intent.side.value,
            )
        except Exception:
            # Race / unique conflict
            await self._reconcile_existing(None, intent.order_link_id, fields, symbol=intent.symbol)
            return

        log_event(
            logger,
            logging.INFO,
            "trading.execution.reserved",
            "Execution reserved in durable journal",
            **fields,
        )

        # If an order with this link already exists on exchange, never create another.
        remote = await self._gateway.get_order_by_link_id(intent.symbol, intent.order_link_id)
        if remote is not None:
            log_event(
                logger,
                logging.INFO,
                "trading.execution.reconciled",
                "Found existing Bybit order for orderLinkId",
                bybit_order_id=remote.order_id,
                status=remote.status,
                **fields,
            )
            self._store.update(
                intent.source_event_id,
                status=ExecutionStatus.RECONCILED,
                bybit_order_id=remote.order_id,
                qty=remote.qty,
                avg_price=remote.avg_price,
            )
            await self._finalize_tp_if_filled(intent, remote, tick_size, fields)
            return

        await self._gateway.set_leverage(intent.symbol, intent.leverage)

        self._store.update(
            intent.source_event_id,
            status=ExecutionStatus.SUBMITTING,
            qty=intent.quantity,
            target_margin=intent.target_margin,
            target_notional=intent.target_notional,
        )
        log_event(
            logger,
            logging.INFO,
            "trading.order.submitting",
            "Submitting market order to Bybit",
            qty=str(intent.quantity),
            **fields,
        )

        try:
            submission = await self._gateway.place_order(
                symbol=intent.symbol,
                side=intent.side,
                qty=intent.quantity,
                order_link_id=intent.order_link_id,
                take_profit=intent.provisional_take_profit,
                stop_loss=intent.provisional_stop_loss,
                tp_trigger_by=intent.tp_trigger_by if intent.provisional_take_profit else None,
                sl_trigger_by=(intent.tp_trigger_by if intent.provisional_stop_loss else None),
            )
        except OrderUncertainError:
            remote = await self._gateway.get_order_by_link_id(intent.symbol, intent.order_link_id)
            if remote is None:
                self._store.update(
                    intent.source_event_id,
                    status=ExecutionStatus.FAILED,
                    error_code="order_uncertain",
                    error_message="create uncertain and order not found",
                )
                raise
            submission_order_id = remote.order_id
            log_event(
                logger,
                logging.INFO,
                "trading.execution.reconciled",
                "Reconciled uncertain create via orderLinkId",
                bybit_order_id=submission_order_id,
                **fields,
            )
            self._store.update(
                intent.source_event_id,
                status=ExecutionStatus.RECONCILED,
                bybit_order_id=submission_order_id,
            )
            await self._finalize_tp_if_filled(intent, remote, tick_size, fields)
            return

        self._store.update(
            intent.source_event_id,
            status=ExecutionStatus.SUBMITTED,
            bybit_order_id=submission.order_id,
            qty=intent.quantity,
            target_margin=intent.target_margin,
            target_notional=intent.target_notional,
        )
        log_event(
            logger,
            logging.INFO,
            "trading.order.submitted",
            "Bybit accepted order create",
            bybit_order_id=submission.order_id,
            **fields,
        )
        await self._announce(
            OrderNotice(
                symbol=intent.symbol,
                kind=OrderUpdateKind.SUBMITTED,
                side=intent.side.value,
                qty=str(intent.quantity),
            )
        )

        fill = await self._gateway.wait_for_fill(
            symbol=intent.symbol,
            order_link_id=intent.order_link_id,
            timeout_sec=self._settings.order_fill_timeout_sec,
        )
        status = (
            ExecutionStatus.FILLED
            if fill.status.lower() in {"filled", "partiallyfilled"}
            or (fill.filled_qty > 0 and fill.avg_price is not None)
            else ExecutionStatus.SUBMITTED
        )
        if fill.filled_qty > 0 and fill.filled_qty < fill.qty:
            status = ExecutionStatus.PARTIALLY_FILLED
            log_event(
                logger,
                logging.INFO,
                "trading.order.partially_filled",
                "Order partially filled",
                filled_qty=str(fill.filled_qty),
                avg_price=str(fill.avg_price) if fill.avg_price else None,
                bybit_order_id=fill.order_id,
                **fields,
            )
        else:
            log_event(
                logger,
                logging.INFO,
                "trading.order.filled",
                "Order filled",
                filled_qty=str(fill.filled_qty),
                avg_price=str(fill.avg_price) if fill.avg_price else None,
                bybit_order_id=fill.order_id,
                **fields,
            )

        self._store.update(
            intent.source_event_id,
            status=status,
            bybit_order_id=fill.order_id,
            avg_price=fill.avg_price,
            qty=fill.filled_qty or intent.quantity,
        )
        await self._finalize_tp_if_filled(intent, fill, tick_size, fields, announce=True)

    async def _finalize_tp_if_filled(
        self,
        intent: TradeIntent,
        fill: object,
        tick_size: Decimal,
        fields: dict[str, object],
        *,
        announce: bool = False,
    ) -> None:
        avg_price = getattr(fill, "avg_price", None)
        filled_qty = getattr(fill, "filled_qty", Decimal("0")) or Decimal("0")
        if avg_price is None or filled_qty <= 0:
            return

        tp_price: Decimal | None = None
        sl_price: Decimal | None = None
        if intent.take_profit_pct is not None:
            tp_price = calc_take_profit_price(
                avg_entry=avg_price,
                take_profit_pct=intent.take_profit_pct,
                direction=intent.direction,
                tick_size=tick_size,
            )
        if intent.stop_loss_pct is not None:
            sl_price = calc_stop_loss_price(
                avg_entry=avg_price,
                stop_loss_pct=intent.stop_loss_pct,
                direction=intent.direction,
                tick_size=tick_size,
            )

        if tp_price is None and sl_price is None:
            self._store.update(intent.source_event_id, status=ExecutionStatus.COMPLETED)
            log_event(
                logger,
                logging.INFO,
                "trading.execution.completed",
                "Execution completed without TP/SL",
                **fields,
            )
            if announce:
                await self._announce(
                    OrderNotice(
                        symbol=intent.symbol,
                        kind=OrderUpdateKind.FILLED,
                        side=intent.side.value,
                        qty=str(filled_qty),
                        avg_price=str(avg_price),
                    )
                )
            return

        plan = TakeProfitPlan(
            take_profit_price=tp_price,
            stop_loss_price=sl_price,
            tp_trigger_by=intent.tp_trigger_by,
            sl_trigger_by=intent.tp_trigger_by if sl_price is not None else None,
        )
        await self._gateway.set_trading_stop(symbol=intent.symbol, plan=plan)
        self._store.update(
            intent.source_event_id,
            status=ExecutionStatus.COMPLETED,
            take_profit_price=tp_price,
            avg_price=avg_price,
        )
        log_event(
            logger,
            logging.INFO,
            "trading.take_profit.set",
            "Take profit / stop loss installed from avg entry",
            take_profit=str(tp_price) if tp_price else None,
            stop_loss=str(sl_price) if sl_price else None,
            avg_price=str(avg_price),
            **fields,
        )
        log_event(
            logger,
            logging.INFO,
            "trading.execution.completed",
            "Execution completed",
            **fields,
        )
        if announce:
            await self._announce(
                OrderNotice(
                    symbol=intent.symbol,
                    kind=OrderUpdateKind.FILLED,
                    side=intent.side.value,
                    qty=str(filled_qty),
                    avg_price=str(avg_price),
                    take_profit=str(tp_price) if tp_price else None,
                    stop_loss=str(sl_price) if sl_price else None,
                )
            )

    async def _reconcile_existing(
        self,
        event: TelegramMessageEvent | None,
        order_link_id: str,
        base_fields: dict[str, object],
        *,
        symbol: str | None = None,
    ) -> None:
        record = self._store.get_by_order_link_id(order_link_id)
        sym = symbol or (record.symbol if record else None)
        log_event(
            logger,
            logging.INFO,
            "trading.execution.reconciled",
            "Duplicate event — reconciling existing execution, not creating new order",
            order_link_id=order_link_id,
            prior_status=record.status.value if record else None,
            symbol=sym,
            **base_fields,
        )
        if sym:
            remote = await self._gateway.get_order_by_link_id(sym, order_link_id)
            if remote is not None and record is not None:
                self._store.update(
                    record.event_id,
                    status=ExecutionStatus.RECONCILED,
                    bybit_order_id=remote.order_id,
                    avg_price=remote.avg_price,
                    qty=remote.filled_qty or remote.qty,
                )

    async def _announce(self, notice: OrderNotice) -> None:
        try:
            await self._notifier.order_update(notice)
        except Exception as exc:  # noqa: BLE001 — notification must not stop trading
            log_event(
                logger,
                logging.WARNING,
                "bot.notify.failed",
                "Order notification failed",
                error_type=type(exc).__name__,
            )

    @staticmethod
    def _reacts_to(signal_type: TradingSignalType, runtime: RuntimeTradingConfig) -> bool:
        if signal_type is TradingSignalType.DUMP:
            return runtime.react_dump
        if signal_type is TradingSignalType.PUMP:
            return runtime.react_pump
        if signal_type is TradingSignalType.SHORT:
            return runtime.react_short
        return False

    @staticmethod
    def _map_side(action: TradeAction) -> tuple[OrderSide, PositionDirection]:
        if action is TradeAction.BUY:
            return OrderSide.BUY, PositionDirection.LONG
        return OrderSide.SELL, PositionDirection.SHORT
